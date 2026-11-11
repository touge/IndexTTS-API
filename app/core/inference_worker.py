# -*- coding: utf-8 -*-
"""
独立 GPU 推理子进程管理与执行入口
====================================
设计原则：
1. 本模块顶层严禁导入 torch / indextts / faster_whisper 等 CUDA 依赖，
   确保 FastAPI 主进程常驻运行时显存占用恒为 0 MB。
2. 所有模型加载与推理均通过 multiprocessing('spawn') 隔离到独立子进程中执行。
3. 当空闲超时、任务取消或网关调用 /free 时销毁子进程，由操作系统 100% 物理回收显存与 CUDA Context。
"""

import logging
import multiprocessing as mp
import os
import queue
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _chunk_text(text: str, max_chars: int = 300) -> list[str]:
    """长文本按段落和标点切分，避免单次推理显存溢出。"""
    import re

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    for p in paragraphs:
        if len(p) <= max_chars:
            chunks.append(p)
            continue

        sentences = re.split(r"(?<=[。！？；!?])", p)
        current_chunk = ""
        for sentence in sentences:
            if not sentence.strip():
                continue
            if len(current_chunk) + len(sentence) <= max_chars:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(sentence) > max_chars:
                    sub_sentences = re.split(r"(?<=[，、,])", sentence)
                    sub_chunk = ""
                    for sub_s in sub_sentences:
                        if not sub_s.strip():
                            continue
                        if len(sub_chunk) + len(sub_s) <= max_chars:
                            sub_chunk += sub_s
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = sub_s
                    current_chunk = sub_chunk
                else:
                    current_chunk = sentence
        if current_chunk:
            chunks.append(current_chunk)
    return [c for c in chunks if c.strip()]


def worker_main(cmd_queue: mp.Queue, event_queue: mp.Queue, project_root: str) -> None:
    """独立 GPU Worker 子进程主循环。所有 CUDA/PyTorch 库均仅在此进程内延迟导入。"""
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    vendor_dir = os.path.join(project_root, "vendor")
    if os.path.exists(vendor_dir) and vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    wlog = logging.getLogger("app.core.inference_worker")
    wlog.info(f"GPU inference worker started (PID={os.getpid()})")

    import gc
    import importlib
    import numpy as np
    import soundfile as sf
    import torch
    from app.utils.yaml_config_loader import YamlConfigLoader

    models: Dict[str, Any] = {}
    current_version: Optional[str] = None

    def _unload_tts(version: Optional[str]) -> None:
        nonlocal current_version
        if not version or version not in models:
            return
        wlog.info(f"Unloading TTS model: {version}")
        model = models.pop(version)
        try:
            if hasattr(model, "release_resources"):
                model.release_resources()
            else:
                if hasattr(model, "to"):
                    try:
                        model.to("cpu")
                    except Exception:
                        pass
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                gc.collect()
        except Exception as e:
            wlog.warning(f"Error unloading TTS model {version}: {e}")
        if current_version == version:
            current_version = None

    def _unload_whisper() -> None:
        try:
            from app.core.subtitle.whisper_manager import WhisperManager

            wm = WhisperManager()
            if wm.model is not None:
                wm.release_resources()
        except Exception as e:
            wlog.warning(f"Error unloading Whisper model: {e}")

    def _load_tts(version: str, tts_cfg: Dict[str, Any]) -> Any:
        nonlocal current_version
        if current_version and current_version != version:
            _unload_tts(current_version)

        if version in models:
            current_version = version
            return models[version]

        models_root_rel = tts_cfg.get("paths", {}).get("models_root", "models")
        models_root = os.path.join(project_root, models_root_rel)
        versions_cfg = tts_cfg.get("versions", {})
        version_cfg = versions_cfg.get(version)
        if not version_cfg:
            raise ValueError(f"Unknown TTS model version: {version}")

        module_name = version_cfg["module"]
        class_name = version_cfg["class_name"]
        model_dir_rel = version_cfg["model_dir"]
        full_model_dir = os.path.join(models_root, os.path.basename(model_dir_rel))
        config_file_name = version_cfg.get("config_file", "config.yaml")
        if not isinstance(config_file_name, str):
            config_file_name = "config.yaml"
        full_config_path = os.path.join(full_model_dir, config_file_name)

        wlog.info(f"Loading TTS model {version} ({module_name}.{class_name}) from {full_model_dir}")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)

        if version in ("V1.5", "V2.0"):
            instance = cls(
                cfg_path=full_config_path,
                model_dir=full_model_dir,
                use_fp16=True,
                device="cuda",
            )
        else:
            instance = cls()

        models[version] = instance
        current_version = version
        wlog.info(f"TTS model {version} loaded.")
        return instance

    def _run_tts(cmd: Dict[str, Any]) -> None:
        task_id = cmd["task_id"]
        version = cmd["engine_version"]
        params = cmd["params"]

        cfg_loader = YamlConfigLoader("config.yaml")
        tts_cfg = cfg_loader.data.get("tts", {})

        event_queue.put({
            "type": "progress",
            "task_id": task_id,
            "current_chunk": 0,
            "total_chunks": 0,
            "progress": 5,
            "message": f"正在加载 {version} 语音模型...",
            "loaded_version": version,
        })

        model = _load_tts(version, tts_cfg)

        output_path = params.get("output_path")
        if not output_path:
            os.makedirs("outputs", exist_ok=True)
            output_path = os.path.join("outputs", f"{task_id}.wav")

        original_text = params["text"]
        text_chunks = _chunk_text(original_text)
        total_chunks = max(len(text_chunks), 1)
        need_sub = bool(params.get("generate_subtitle", False))
        max_chunk_pct = 75 if need_sub else 92

        temp_files = []
        try:
            for idx, chunk in enumerate(text_chunks):
                event_queue.put({
                    "type": "progress",
                    "task_id": task_id,
                    "current_chunk": idx + 1,
                    "total_chunks": len(text_chunks),
                    "progress": min(max_chunk_pct, 5 + int((max_chunk_pct - 5) * (idx / total_chunks))),
                    "message": f"正在合成文本分段 ({idx + 1}/{len(text_chunks)})",
                    "loaded_version": version,
                })

                chunk_output = output_path.replace(".wav", f"_chunk_{idx}.wav")
                temp_files.append(chunk_output)

                if version == "V1.5":
                    infer_params = params.copy()
                    infer_params["text"] = chunk
                    if "spk_audio_prompt" in infer_params:
                        infer_params["audio_prompt"] = infer_params.pop("spk_audio_prompt")
                    valid_keys = ["text", "audio_prompt", "output_path", "verbose", "max_text_tokens_per_segment"]
                    call_kwargs = {k: v for k, v in infer_params.items() if k in valid_keys}
                    extra_keys = [
                        "top_k", "top_p", "temperature", "do_sample",
                        "length_penalty", "repetition_penalty", "num_beams", "max_mel_tokens",
                    ]
                    for k in extra_keys:
                        if k in infer_params:
                            call_kwargs[k] = infer_params[k]
                    call_kwargs["output_path"] = chunk_output
                    model.infer(**call_kwargs)
                elif version == "V2.0":
                    infer_params = params.copy()
                    infer_params["text"] = chunk
                    if infer_params.get("use_emo_text", False) and not infer_params.get("emo_text"):
                        infer_params["emo_text"] = chunk
                    valid_keys = [
                        "spk_audio_prompt", "text", "output_path",
                        "emo_audio_prompt", "emo_alpha", "emo_vector",
                        "use_emo_text", "emo_text", "use_random",
                        "interval_silence", "verbose", "max_text_tokens_per_segment",
                    ]
                    call_kwargs = {k: v for k, v in infer_params.items() if k in valid_keys}
                    extra_keys = [
                        "top_k", "top_p", "temperature", "do_sample",
                        "length_penalty", "repetition_penalty", "num_beams", "max_mel_tokens",
                    ]
                    for k in extra_keys:
                        if k in infer_params:
                            call_kwargs[k] = infer_params[k]
                    call_kwargs["output_path"] = chunk_output
                    model.infer(**call_kwargs)
                else:
                    raise ValueError(f"Unsupported version: {version}")

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                event_queue.put({
                    "type": "progress",
                    "task_id": task_id,
                    "current_chunk": idx + 1,
                    "total_chunks": len(text_chunks),
                    "progress": min(max_chunk_pct, 5 + int((max_chunk_pct - 5) * ((idx + 1) / total_chunks))),
                    "message": f"已完成文本分段 ({idx + 1}/{len(text_chunks)})",
                    "loaded_version": version,
                })

            combined_audio = []
            sample_rate = 22050
            interval_ms = params.get("interval_silence", 200)
            for fpath in temp_files:
                if os.path.exists(fpath):
                    audio_data, sr = sf.read(fpath)
                    sample_rate = sr
                    combined_audio.append(audio_data)
                    if interval_ms > 0:
                        silence = np.zeros(int(sr * interval_ms / 1000.0), dtype=audio_data.dtype)
                        combined_audio.append(silence)

            if interval_ms > 0 and len(combined_audio) > 1:
                combined_audio.pop()

            if not combined_audio:
                raise RuntimeError("No audio chunks generated or read successfully.")

            final_audio = np.concatenate(combined_audio)
            sf.write(output_path, final_audio, sample_rate, subtype="PCM_16")
        finally:
            for fpath in temp_files:
                if os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

        subtitle_path = None
        if need_sub:
            event_queue.put({
                "type": "progress",
                "task_id": task_id,
                "current_chunk": len(text_chunks),
                "total_chunks": len(text_chunks),
                "progress": 82,
                "message": "正在生成字幕对齐...",
                "loaded_version": version,
                "whisper_loaded": True,
            })
            try:
                from app.core.subtitle.subtitle_generator import SubtitleGenerator

                sub_out = output_path.replace(".wav", ".srt")
                SubtitleGenerator().generate(
                    audio_path=output_path,
                    original_text=original_text,
                    output_srt_path=sub_out,
                )
                subtitle_path = sub_out
            except Exception as sub_err:
                wlog.error(f"Subtitle generation failed (ignored): {sub_err}", exc_info=True)

        event_queue.put({
            "type": "done",
            "task_id": task_id,
            "result": output_path,
            "subtitle_path": subtitle_path,
            "loaded_version": current_version,
        })

    def _run_subtitle(cmd: Dict[str, Any]) -> None:
        task_id = cmd["task_id"]
        params = cmd["params"]

        event_queue.put({
            "type": "progress",
            "task_id": task_id,
            "progress": 15,
            "message": "正在加载 Whisper 模型并转录音频...",
            "whisper_loaded": True,
        })

        from app.core.subtitle.subtitle_generator import SubtitleGenerator

        subtitle_path = SubtitleGenerator().generate(
            audio_path=params["audio_path"],
            original_text=params["text"],
            output_srt_path=params["output_path"],
        )

        event_queue.put({
            "type": "progress",
            "task_id": task_id,
            "progress": 95,
            "message": "字幕对齐完成，正在整理输出...",
            "whisper_loaded": True,
        })
        event_queue.put({
            "type": "done",
            "task_id": task_id,
            "result": None,
            "subtitle_path": subtitle_path,
            "whisper_loaded": True,
        })

    def _run_preload(cmd: Dict[str, Any]) -> None:
        task_id = cmd.get("task_id", "preload")
        version = cmd.get("engine_version")
        load_subtitle = bool(cmd.get("subtitle", False))

        cfg_loader = YamlConfigLoader("config.yaml")
        tts_cfg = cfg_loader.data.get("tts", {})

        if version:
            _load_tts(version, tts_cfg)
        if load_subtitle:
            from app.core.subtitle.whisper_manager import WhisperManager

            subtitle_cfg = tts_cfg.get("subtitle", {})
            models_root = tts_cfg.get("paths", {}).get("models_root", "models")
            whisper_path = os.path.join(models_root, subtitle_cfg.get("whisper_model", "whisper/faster-whisper-large-v2"))
            WhisperManager().load_model(whisper_path)

        event_queue.put({
            "type": "preloaded",
            "task_id": task_id,
            "loaded_version": current_version,
            "whisper_loaded": load_subtitle,
        })

    while True:
        cmd = cmd_queue.get()
        if not isinstance(cmd, dict):
            continue
        op = cmd.get("cmd")
        if op == "shutdown":
            wlog.info("Shutdown command received, releasing GPU models and exiting worker.")
            _unload_tts(current_version)
            _unload_whisper()
            break
        try:
            if op == "run_tts":
                _run_tts(cmd)
            elif op == "run_subtitle":
                _run_subtitle(cmd)
            elif op == "preload":
                _run_preload(cmd)
            else:
                raise ValueError(f"Unknown worker command: {op}")
        except Exception as e:
            wlog.error(f"Worker command '{op}' failed: {e}", exc_info=True)
            event_queue.put({
                "type": "error",
                "task_id": cmd.get("task_id"),
                "error": str(e),
            })

    wlog.info("GPU inference worker exited cleanly.")


class WorkerProcessManager:
    """在主进程中管理 spawn 隔离的 GPU 推理子进程。"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or str(Path(__file__).resolve().parents[2])
        self._ctx = mp.get_context("spawn")
        self._proc: Optional[mp.Process] = None
        self._cmd_queue: Optional[mp.Queue] = None
        self._event_queue: Optional[mp.Queue] = None

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc and self._proc.is_alive() else None

    @property
    def exitcode(self) -> Optional[int]:
        return self._proc.exitcode if self._proc else None

    def ensure_started(self) -> None:
        if self.is_alive():
            return
        self.cleanup_dead()
        self._cmd_queue = self._ctx.Queue()
        self._event_queue = self._ctx.Queue()
        self._proc = self._ctx.Process(
            target=worker_main,
            args=(self._cmd_queue, self._event_queue, self.project_root),
            daemon=True,
            name="IndexTTSGPUWorker",
        )
        self._proc.start()
        logger.info(f"[WorkerManager] Spawned GPU worker process PID={self._proc.pid}")

    def send(self, cmd: Dict[str, Any]) -> None:
        self.ensure_started()
        assert self._cmd_queue is not None
        self._cmd_queue.put(cmd)

    def recv(self, timeout: float = 0.25) -> Optional[Dict[str, Any]]:
        if not self._event_queue:
            return None
        try:
            return self._event_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def cleanup_dead(self) -> None:
        if self._proc is not None and not self._proc.is_alive():
            try:
                self._proc.join(timeout=0.5)
            except Exception:
                pass
            self._close_queues()
            self._proc = None

    def stop(self, force: bool = False, wait_timeout: float = 3.0) -> bool:
        if self._proc is None:
            self._close_queues()
            return False

        was_alive = self._proc.is_alive()
        if was_alive and not force and self._cmd_queue is not None:
            try:
                self._cmd_queue.put({"cmd": "shutdown"})
                self._proc.join(timeout=wait_timeout)
            except Exception as e:
                logger.warning(f"[WorkerManager] Graceful shutdown wait failed: {e}")

        if self._proc.is_alive():
            logger.warning(f"[WorkerManager] Terminating GPU worker PID={self._proc.pid} (force={force})")
            try:
                self._proc.terminate()
                self._proc.join(timeout=2.0)
            except Exception:
                pass

        if self._proc.is_alive():
            logger.error(f"[WorkerManager] Killing GPU worker PID={self._proc.pid}")
            try:
                self._proc.kill()
                self._proc.join(timeout=1.0)
            except Exception:
                pass

        self._close_queues()
        self._proc = None
        return was_alive

    def _close_queues(self) -> None:
        for q in (self._cmd_queue, self._event_queue):
            if q is not None:
                try:
                    q.close()
                    q.cancel_join_thread()
                except Exception:
                    pass
        self._cmd_queue = None
        self._event_queue = None

