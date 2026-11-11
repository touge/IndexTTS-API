# -*- coding: utf-8 -*-
"""
任务队列与 GPU Worker 生命周期管理器
====================================
架构特性：
1. Web 主进程绝不初始化 CUDA（0 MB 显存常驻），随时响应查询、资源管理、试听与下载。
2. 所有模型推理通过 WorkerProcessManager 隔离在 spawn 独立子进程中执行。
3. 仅在配置允许时才按需加载模型；任务空闲超时或收到 /free 后立即销毁子进程，显存 100% 物理归零。
"""

import asyncio
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.core.inference_worker import WorkerProcessManager
from app.utils.yaml_config_loader import yaml_config_loader

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(Enum):
    """任务类型枚举"""
    TTS = "tts"
    SUBTITLE = "subtitle"


class TTSEngine(Enum):
    """TTS 引擎类型枚举"""
    INDEXTTS = "indextts"
    COSYVOICE = "cosyvoice"


@dataclass
class TaskRequest:
    """统一的任务请求数据类"""
    task_id: str
    task_type: TaskType
    tts_engine: Optional[TTSEngine] = None
    engine_version: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    subtitle_path: Optional[str] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    current_chunk: int = 0
    total_chunks: int = 0
    progress: int = 0
    progress_message: str = ""


class QueueManager:
    def __init__(self, worker_manager: Optional[WorkerProcessManager] = None):
        self.queue: Optional[asyncio.Queue] = None
        self.tasks: Dict[str, TaskRequest] = {}
        self.worker_task: Optional[asyncio.Task] = None
        self._idle_timer_task: Optional[asyncio.Task] = None
        self._ipc_executor: Optional[ThreadPoolExecutor] = None
        self.worker_manager = worker_manager or WorkerProcessManager()

        # 运行时状态（全部在主进程跟踪，主进程本身不接触 CUDA）
        self.active_task_id: Optional[str] = None
        self.loaded_version: Optional[str] = None
        self.whisper_loaded: bool = False
        self._cancelled_tasks: set[str] = set()
        self._free_pending: bool = False

        # 模型按需加载与显存回收配置
        cfg_versions = yaml_config_loader.get("tts.model.enabled_versions", ["V1.5", "V2.0"])
        self.enabled_versions: List[str] = list(cfg_versions) if cfg_versions is not None else []
        self.preload_version: Optional[str] = yaml_config_loader.get("tts.model.preload_version", None)
        self.subtitle_enabled: bool = bool(yaml_config_loader.get("tts.model.subtitle_enabled", True))
        self.unload_after_gen: bool = bool(
            yaml_config_loader.get("tts.model.runtime_settings.unload_after_gen", True)
        )
        self.idle_unload_seconds: int = int(yaml_config_loader.get("tts.model.idle_unload_seconds", 15))

    def _ensure_executor(self) -> ThreadPoolExecutor:
        if self._ipc_executor is None:
            self._ipc_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="WorkerIPC")
        return self._ipc_executor

    async def start(self):
        """启动队列处理循环（默认 0 显存待命，仅当配置显式指定 preload_version 时才预热）"""
        self.queue = asyncio.Queue()
        self._ensure_executor()
        self.worker_task = asyncio.create_task(self._process_queue())
        logger.info(
            "TTS Queue Manager started (0-VRAM main process, "
            f"enabled_versions={self.enabled_versions}, preload_version={self.preload_version}, "
            f"subtitle_enabled={self.subtitle_enabled})."
        )
        if self.preload_version:
            if self.preload_version in self.enabled_versions:
                try:
                    await self.preload_models(version=self.preload_version, load_subtitle=False)
                except Exception as e:
                    logger.error(f"Startup preload failed for {self.preload_version}: {e}")
            else:
                logger.warning(
                    f"preload_version '{self.preload_version}' is not in enabled_versions {self.enabled_versions}, skipping."
                )

    async def stop(self):
        """停止队列处理并回收 GPU Worker 子进程"""
        self._cancel_idle_timer()
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
            self.worker_task = None
        loop = asyncio.get_running_loop()
        if self._ipc_executor is not None:
            await loop.run_in_executor(self._ipc_executor, self.worker_manager.stop, False, 3.0)
            self._ipc_executor.shutdown(wait=True)
            self._ipc_executor = None
        else:
            self.worker_manager.stop(False, 3.0)
        self.loaded_version = None
        self.whisper_loaded = False
        logger.info("TTS Queue Manager stopped.")

    def _cancel_idle_timer(self) -> None:
        if self._idle_timer_task and not self._idle_timer_task.done():
            self._idle_timer_task.cancel()
        self._idle_timer_task = None

    def _schedule_idle_unload(self) -> None:
        self._cancel_idle_timer()
        if not self.unload_after_gen or self.idle_unload_seconds <= 0:
            return
        if not self.worker_manager.is_alive():
            return

        async def _timer():
            try:
                await asyncio.sleep(self.idle_unload_seconds)
                if self.active_task_id is None and self.queue.empty():
                    logger.info(
                        f"Queue idle for {self.idle_unload_seconds}s, stopping GPU worker to release VRAM..."
                    )
                    await self._teardown_worker(force=False)
            except asyncio.CancelledError:
                pass

        self._idle_timer_task = asyncio.create_task(_timer())

    async def _teardown_worker(self, force: bool = False) -> bool:
        self._cancel_idle_timer()
        loop = asyncio.get_running_loop()
        was_alive = await loop.run_in_executor(self._ensure_executor(), self.worker_manager.stop, force, 3.0)
        self.loaded_version = None
        self.whisper_loaded = False
        return was_alive

    def _validate_task_allowed(
        self, task_type: TaskType, tts_engine: Optional[TTSEngine], engine_version: Optional[str], params: Dict[str, Any]
    ) -> None:
        if task_type == TaskType.TTS:
            if not tts_engine:
                raise ValueError("TTS task requires 'tts_engine' parameter")
            if tts_engine == TTSEngine.COSYVOICE:
                raise ValueError("CosyVoice engine is not yet implemented")
            if tts_engine == TTSEngine.INDEXTTS:
                if not engine_version or engine_version not in self.enabled_versions:
                    raise ValueError(
                        f"Model version '{engine_version}' is disabled or not configured "
                        f"(enabled_versions={self.enabled_versions})"
                    )
            if params.get("generate_subtitle") and not self.subtitle_enabled:
                raise ValueError("Subtitle generation is disabled by configuration (subtitle_enabled=false)")
        elif task_type == TaskType.SUBTITLE:
            if not self.subtitle_enabled:
                raise ValueError("Subtitle generation is disabled by configuration (subtitle_enabled=false)")

    async def submit_task(
        self,
        task_type: TaskType,
        params: Dict[str, Any],
        **task_options,
    ) -> str:
        """提交一个新任务到异步队列（仅配置允许的模型才会进入执行）。"""
        tts_engine = task_options.get("tts_engine")
        engine_version = task_options.get("engine_version")

        self._validate_task_allowed(task_type, tts_engine, engine_version, params)

        task_id = str(uuid.uuid4())
        tasks_dir = yaml_config_loader.get("api.output.tasks_dir", "output/tasks")
        task_output_dir = os.path.join(tasks_dir, task_id)
        os.makedirs(task_output_dir, exist_ok=True)

        if task_type == TaskType.SUBTITLE:
            output_filename = params.get("output_filename", "subtitle.srt")
            params["output_path"] = os.path.join(task_output_dir, output_filename)
            if "audio_content" in params:
                audio_ext = params.get("audio_ext", ".wav")
                audio_path = os.path.join(task_output_dir, f"uploaded_audio{audio_ext}")
                with open(audio_path, "wb") as f:
                    f.write(params["audio_content"])
                params["audio_path"] = audio_path
                del params["audio_content"]
                del params["audio_ext"]
                logger.info(f"Audio file saved to task directory: {audio_path}")
        elif task_type == TaskType.TTS:
            params["output_path"] = os.path.join(task_output_dir, f"{task_id}.wav")
        else:
            raise ValueError(f"Unsupported task type: {task_type}")

        self._cancel_idle_timer()
        request = TaskRequest(
            task_id=task_id,
            task_type=task_type,
            tts_engine=tts_engine,
            engine_version=engine_version,
            params=params,
            progress=0,
            progress_message="任务已入队等待执行",
        )
        if self.queue is None:
            self.queue = asyncio.Queue()
        self.tasks[task_id] = request
        await self.queue.put(request)

        log_msg = f"Task submitted: {task_id} (Type: {task_type.value}"
        if tts_engine:
            log_msg += f", Engine: {tts_engine.value}"
            if engine_version:
                log_msg += f", Version: {engine_version}"
        log_msg += ")"
        logger.info(log_msg)
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态与进度详情"""
        task = self.tasks.get(task_id)
        if not task:
            return None

        queue_position = None
        queue_size = self.queue.qsize() if self.queue is not None else 0
        if task.status == TaskStatus.PROCESSING:
            queue_position = 0
        elif task.status == TaskStatus.PENDING:
            queue_position = self._get_queue_position(task_id)

        created_at_str = datetime.fromtimestamp(task.created_at).strftime("%Y-%m-%d %H:%M:%S")
        download_url = None
        file_url = None
        subtitle_url = None
        if task.status == TaskStatus.COMPLETED:
            if task.result:
                download_url = f"/download/{task.task_id}"
                file_url = f"/files/{task.task_id}"
            if task.subtitle_path:
                subtitle_url = f"/download/subtitle/{task.task_id}"

        data: Dict[str, Any] = {
            "task_id": task.task_id,
            "created_at": created_at_str,
            "error": task.error,
            "queue_position": queue_position,
            "queue_size": queue_size,
            "created_timestamp": task.created_at,
            "progress": task.progress,
            "download_url": download_url,
            "file_url": file_url,
            "subtitle_url": subtitle_url,
        }
        if task.current_chunk > 0:
            data["current_chunk"] = task.current_chunk
            data["total_chunks"] = task.total_chunks

        return {
            "status": task.status.value,
            "message": task.progress_message or "查询成功",
            "progress": task.progress,
            "data": data,
        }

    def _get_queue_position(self, task_id: str) -> int:
        pending_tasks = [t for t in self.tasks.values() if t.status == TaskStatus.PENDING]
        pending_tasks.sort(key=lambda t: t.created_at)
        for idx, task in enumerate(pending_tasks, start=1):
            if task.task_id == task_id:
                return idx
        return 1

    async def _process_queue(self):
        """后台队列消费循环，委托隔离 GPU Worker 执行任务"""
        loop = asyncio.get_running_loop()
        while True:
            try:
                request = await self.queue.get()
                self._cancel_idle_timer()

                if request.status == TaskStatus.FAILED or request.task_id in self._cancelled_tasks:
                    logger.info(f"Skipping already cancelled task: {request.task_id}")
                    self.queue.task_done()
                    continue

                request.status = TaskStatus.PROCESSING
                request.progress = 2
                request.progress_message = "正在分配 GPU 推理进程..."
                self.active_task_id = request.task_id
                logger.info(f"Processing task: {request.task_id}")

                try:
                    if request.task_type == TaskType.SUBTITLE:
                        cmd = {
                            "cmd": "run_subtitle",
                            "task_id": request.task_id,
                            "params": request.params,
                        }
                    elif request.task_type == TaskType.TTS:
                        cmd = {
                            "cmd": "run_tts",
                            "task_id": request.task_id,
                            "engine_version": request.engine_version,
                            "params": request.params,
                        }
                    else:
                        raise ValueError(f"Unknown task type: {request.task_type}")

                    await loop.run_in_executor(self._ensure_executor(), self.worker_manager.send, cmd)

                    while True:
                        if request.task_id in self._cancelled_tasks:
                            logger.info(f"Task {request.task_id} aborted by cancellation.")
                            break

                        event = await loop.run_in_executor(self._ensure_executor(), self.worker_manager.recv, 0.25)
                        if event is None:
                            if request.task_id in self._cancelled_tasks:
                                break
                            if not self.worker_manager.is_alive():
                                raise RuntimeError(
                                    f"GPU inference worker exited unexpectedly (exitcode={self.worker_manager.exitcode})"
                                )
                            continue

                        if event.get("task_id") != request.task_id:
                            continue

                        etype = event.get("type")
                        if etype == "progress":
                            if "current_chunk" in event:
                                request.current_chunk = int(event["current_chunk"] or 0)
                            if "total_chunks" in event:
                                request.total_chunks = int(event["total_chunks"] or 0)
                            if event.get("progress") is not None:
                                request.progress = int(event["progress"])
                            if event.get("message"):
                                request.progress_message = event["message"]
                            if event.get("loaded_version"):
                                self.loaded_version = event["loaded_version"]
                            if event.get("whisper_loaded"):
                                self.whisper_loaded = True
                        elif etype == "done":
                            request.result = event.get("result")
                            request.subtitle_path = event.get("subtitle_path")
                            if event.get("loaded_version"):
                                self.loaded_version = event["loaded_version"]
                            if event.get("whisper_loaded"):
                                self.whisper_loaded = True
                            request.progress = 100
                            request.progress_message = "生成完成"
                            request.status = TaskStatus.COMPLETED
                            logger.info(f"Task completed: {request.task_id}")
                            break
                        elif etype == "error":
                            raise RuntimeError(event.get("error", "Unknown worker error"))

                except Exception as e:
                    if request.task_id not in self._cancelled_tasks:
                        logger.error(f"Task failed: {request.task_id} - {e}", exc_info=True)
                        request.error = str(e)
                        request.progress_message = str(e)
                        request.status = TaskStatus.FAILED
                finally:
                    self.active_task_id = None
                    self.queue.task_done()
                    if self._free_pending and self.queue.empty():
                        self._free_pending = False
                        logger.info("Executing deferred /free: destroying GPU worker...")
                        await self._teardown_worker(force=False)
                    elif self.queue.empty():
                        self._schedule_idle_unload()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def cancel_task(self, task_id: str) -> Tuple[bool, str]:
        """取消排队中或正在执行的任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False, "not_found"

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return True, "already_finished"

        self._cancelled_tasks.add(task_id)
        task.error = "任务已被用户手动停止"
        task.progress_message = "任务已被用户手动停止"
        task.status = TaskStatus.FAILED

        if self.active_task_id == task_id:
            logger.warning(f"Cancelling active GPU task {task_id}: terminating worker process...")
            await self._teardown_worker(force=True)
            return True, "cancelled_running"

        logger.info(f"Cancelled queued task {task_id}")
        return True, "cancelled_queued"

    async def free_resources(self) -> Dict[str, Any]:
        """释放 GPU 显存：若空闲则立即销毁 Worker 子进程，若忙碌则标记任务完成后立即销毁"""
        if not self.worker_manager.is_alive():
            self.loaded_version = None
            self.whisper_loaded = False
            self._free_pending = False
            return {
                "freed": True,
                "was_running": False,
                "deferred": False,
                "worker_alive": False,
                "message": "GPU Worker 未运行，显存已处于释放状态",
            }

        if self.active_task_id is not None or not self.queue.empty():
            self._free_pending = True
            return {
                "freed": False,
                "was_running": True,
                "deferred": True,
                "worker_alive": True,
                "message": "当前仍有任务在执行，将在队列清空后立即销毁 GPU Worker 释放显存",
            }

        was_alive = await self._teardown_worker(force=False)
        return {
            "freed": True,
            "was_running": was_alive,
            "deferred": False,
            "worker_alive": self.worker_manager.is_alive(),
            "message": "GPU Worker 已停止，显存已彻底释放",
        }

    async def preload_models(self, version: Optional[str] = None, load_subtitle: bool = False) -> Dict[str, Any]:
        """显式按需预加载指定模型（仅在空闲且配置允许时执行）"""
        if version and version not in self.enabled_versions:
            raise ValueError(f"Model version '{version}' is disabled (enabled_versions={self.enabled_versions})")
        if load_subtitle and not self.subtitle_enabled:
            raise ValueError("Subtitle model loading is disabled (subtitle_enabled=false)")
        if self.active_task_id is not None or not self.queue.empty():
            raise RuntimeError("Cannot preload while queue has active or pending tasks")

        self._cancel_idle_timer()
        loop = asyncio.get_running_loop()
        task_id = f"preload-{uuid.uuid4().hex[:8]}"
        await loop.run_in_executor(
            self._ensure_executor(),
            self.worker_manager.send,
            {
                "cmd": "preload",
                "task_id": task_id,
                "engine_version": version,
                "subtitle": load_subtitle,
            },
        )
        while True:
            event = await loop.run_in_executor(self._ensure_executor(), self.worker_manager.recv, 0.25)
            if event is None:
                if not self.worker_manager.is_alive():
                    raise RuntimeError("GPU worker exited unexpectedly during preload")
                continue
            if event.get("task_id") != task_id:
                continue
            if event.get("type") == "preloaded":
                if event.get("loaded_version"):
                    self.loaded_version = event["loaded_version"]
                if event.get("whisper_loaded"):
                    self.whisper_loaded = True
                return self.get_model_status()
            if event.get("type") == "error":
                raise RuntimeError(event.get("error", "Preload failed"))

    def get_model_status(self) -> Dict[str, Any]:
        """查询当前 Worker 进程、模型加载状态与配置策略"""
        alive = self.worker_manager.is_alive()
        if not alive:
            self.loaded_version = None
            self.whisper_loaded = False
        return {
            "worker_alive": alive,
            "worker_pid": self.worker_manager.pid,
            "loaded_version": self.loaded_version,
            "whisper_loaded": self.whisper_loaded,
            "active_task_id": self.active_task_id,
            "queue_size": self.queue.qsize(),
            "enabled_versions": list(self.enabled_versions),
            "preload_version": self.preload_version,
            "subtitle_enabled": self.subtitle_enabled,
            "unload_after_gen": self.unload_after_gen,
            "idle_unload_seconds": self.idle_unload_seconds,
        }

    async def update_model_config(
        self,
        enabled_versions: Optional[List[str]] = None,
        subtitle_enabled: Optional[bool] = None,
        unload_after_gen: Optional[bool] = None,
        idle_unload_seconds: Optional[int] = None,
        preload_version: Optional[str] = None,
        action: Optional[str] = None,
        version: Optional[str] = None,
        load_subtitle: bool = False,
    ) -> Dict[str, Any]:
        """运行时更新模型加载配置，并支持显式 load / unload 动作"""
        if enabled_versions is not None:
            self.enabled_versions = list(enabled_versions)
        if subtitle_enabled is not None:
            self.subtitle_enabled = bool(subtitle_enabled)
        if unload_after_gen is not None:
            self.unload_after_gen = bool(unload_after_gen)
        if idle_unload_seconds is not None:
            self.idle_unload_seconds = max(0, int(idle_unload_seconds))
        if preload_version is not None:
            self.preload_version = preload_version or None

        if action == "unload":
            await self.free_resources()
        elif action == "load":
            target_ver = version or self.preload_version
            if not target_ver and not load_subtitle:
                raise ValueError("action='load' requires 'version' or 'load_subtitle=true'")
            await self.preload_models(version=target_ver, load_subtitle=load_subtitle)

        return self.get_model_status()
