import asyncio
import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class TaskType(Enum):
    """任务类型枚举"""
    TTS = "tts"              # TTS 生成任务
    SUBTITLE = "subtitle"    # 字幕生成任务

class TTSEngine(Enum):
    """
TTS 引擎类型枚举
    
    支持多种 TTS 引擎，每个引擎可能有不同的版本管理方式
    """
    INDEXTTS = "indextts"    # IndexTTS 引擎（支持 V1.5, V2.0 版本）
    COSYVOICE = "cosyvoice"  # CosyVoice 引擎（可能无版本区分）
    # 未来可以添加更多引擎...

@dataclass
class TaskRequest:
    """统一的任务请求数据类"""
    task_id: str
    task_type: TaskType                         # 任务类型：TTS 或 SUBTITLE
    
    # TTS 任务相关字段（仅 task_type=TTS 时有效）
    tts_engine: Optional[TTSEngine] = None      # TTS 引擎类型（indextts, cosyvoice 等）
    engine_version: Optional[str] = None        # 引擎版本（可选，如 indextts 的 "V1.5"/"V2.0"）
    
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None                # 音频文件路径（TTS 任务）
    subtitle_path: Optional[str] = None         # 字幕文件路径
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    current_chunk: int = 0                      # 当前合成的段落索引
    total_chunks: int = 0                       # 合成文本的总分段数

class QueueManager:
    def __init__(self):
        # 使用 asyncio.Queue 对协程友好，但在 Worker 线程中实际上我们可能需要一个线程安全的队列
        # 或者我们简单地使用 ThreadPoolExecutor 来运行阻塞的任务
        self.queue = asyncio.Queue()
        self.tasks: Dict[str, TaskRequest] = {}
        self.worker_task = None
        self.executor = ThreadPoolExecutor(max_workers=1) # 生成任务通常是显存密集型，限制为 1 个并发
        self.models = {} # 缓存 TTS 模型实例
        self.current_loaded_version = None  # 当前加载的 TTS 模型版本
        
    async def start(self):
        """启动队列处理循环"""
        self.worker_task = asyncio.create_task(self._process_queue())
        logger.info("TTS Queue Manager started.")

    async def stop(self):
        """停止队列处理"""
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        self.executor.shutdown(wait=True)
        logger.info("TTS Queue Manager stopped.")

    async def submit_task(
        self, 
        task_type: TaskType, 
        params: Dict[str, Any],
        **task_options
    ) -> str:
        """
        提交一个新任务
        
        Args:
            task_type: 任务类型（TTS 或 SUBTITLE）
            params: 任务参数
            **task_options: 任务选项（根据任务类型不同）
                TTS 任务:
                    - tts_engine: TTSEngine - TTS 引擎类型（必填）
                    - engine_version: str - 引擎版本（可选）
                SUBTITLE 任务:
                    - 无额外选项
        
        Returns:
            task_id: 任务 ID
            
        Raises:
            ValueError: 如果 TTS 任务未提供 tts_engine
            
        Examples:
            # TTS 任务 (IndexTTS)
            await qm.submit_task(
                task_type=TaskType.TTS,
                params={...},
                tts_engine=TTSEngine.INDEXTTS,
                engine_version="V1.5"
            )
            
            # TTS 任务 (CosyVoice, 无版本)
            await qm.submit_task(
                task_type=TaskType.TTS,
                params={...},
                tts_engine=TTSEngine.COSYVOICE
            )
            
            # 字幕任务
            await qm.submit_task(
                task_type=TaskType.SUBTITLE,
                params={...}
            )
        """
        # 提取任务选项
        tts_engine = task_options.get('tts_engine')
        engine_version = task_options.get('engine_version')
        
        # 验证参数
        if task_type == TaskType.TTS and not tts_engine:
            raise ValueError("TTS task requires 'tts_engine' parameter")
        
        # 生成任务 ID
        task_id = str(uuid.uuid4())
        
        # 强制设置输出路径到 tasks 目录
        from app.utils.yaml_config_loader import yaml_config_loader
        import os
        
        tasks_dir = yaml_config_loader.get('api.output.tasks_dir', 'output/tasks')
        task_output_dir = os.path.join(tasks_dir, task_id)
        os.makedirs(task_output_dir, exist_ok=True)
        
        # 根据任务类型设置输出路径
        if task_type == TaskType.SUBTITLE:
            # 字幕生成任务：输出 .srt 文件
            output_filename = params.get('output_filename', 'subtitle.srt')
            params['output_path'] = os.path.join(task_output_dir, output_filename)
            
            # 如果有音频内容，保存到任务目录
            if 'audio_content' in params:
                audio_ext = params.get('audio_ext', '.wav')
                audio_path = os.path.join(task_output_dir, f"uploaded_audio{audio_ext}")
                with open(audio_path, "wb") as f:
                    f.write(params['audio_content'])
                # 替换参数：从 audio_content 改为 audio_path
                params['audio_path'] = audio_path
                del params['audio_content']
                del params['audio_ext']
                logger.info(f"Audio file saved to task directory: {audio_path}")
        elif task_type == TaskType.TTS:
            # TTS 任务：输出 .wav 文件
            params['output_path'] = os.path.join(task_output_dir, f"{task_id}.wav")
        else:
            raise ValueError(f"Unsupported task type: {task_type}")
        
        logger.info(f"Output path set to: {params['output_path']}")
        
        # 创建任务请求
        request = TaskRequest(
            task_id=task_id,
            task_type=task_type,
            tts_engine=tts_engine,
            engine_version=engine_version,
            params=params
        )
        
        self.tasks[task_id] = request
        await self.queue.put(request)
        
        # 构建日志消息
        log_msg = f"Task submitted: {task_id} (Type: {task_type.value}"
        if tts_engine:
            log_msg += f", Engine: {tts_engine.value}"
            if engine_version:
                log_msg += f", Version: {engine_version}"
        log_msg += ")"
        logger.info(log_msg)
        
        return task_id

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        返回任务的详细状态信息，包括队列位置：
        - queue_position = 0: 正在执行
        - queue_position >= 1: 排队中，数字表示前面还有几个任务
        - queue_position = None: 任务已完成或失败
        """
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        # 计算队列位置
        queue_position = None
        queue_size = self.queue.qsize()
        
        if task.status == TaskStatus.PROCESSING:
            # 正在执行的任务，位置为 0
            queue_position = 0
        elif task.status == TaskStatus.PENDING:
            # 排队中的任务，计算在队列中的位置
            queue_position = self._get_queue_position(task_id)
        # completed 或 failed 状态，queue_position 保持 None
        
        # 格式化时间为人类可读格式
        from datetime import datetime
        created_datetime = datetime.fromtimestamp(task.created_at)
        created_at_str = created_datetime.strftime("%Y-%m-%d %H:%M:%S")
        
        # 生成下载链接（仅 completed 状态）
        download_url = None
        file_url = None
        subtitle_url = None
        if task.status == TaskStatus.COMPLETED:
            # 注意：这里生成的是相对路径，客户端需要拼接完整 URL
            download_url = f"/download/{task.task_id}"
            file_url = f"/files/{task.task_id}"
            # 如果生成了字幕,添加字幕下载链接
            if task.subtitle_path:
                subtitle_url = f"/download/subtitle/{task.task_id}"
        
        response = {
            "status": task.status.value,
            "message": "查询成功",
            "data": {
                "task_id": task.task_id,
                "created_at": created_at_str,
                "error": task.error,
                "queue_position": queue_position,
                "queue_size": queue_size,
                "created_timestamp": task.created_at,
                "download_url": download_url,
                "file_url": file_url,
                "subtitle_url": subtitle_url
            }
        }
        
        # 将进度数值化暴露，便于不同客户端做自定义展示
        if hasattr(task, 'current_chunk') and task.current_chunk > 0:
            response["data"]["current_chunk"] = task.current_chunk
            response["data"]["total_chunks"] = task.total_chunks
            
        # logging.info(f"Task status: {response}")
        return response
    
    def _get_queue_position(self, task_id: str) -> int:
        """
        获取任务在队列中的位置
        
        注意：这个方法会遍历队列，可能有性能影响
        """
        position = 1  # 从 1 开始，因为 0 表示正在执行
        
        # 由于 asyncio.Queue 不支持直接遍历，我们需要另一种方法
        # 简化实现：根据任务创建时间估算位置
        pending_tasks = [
            t for t in self.tasks.values() 
            if t.status == TaskStatus.PENDING
        ]
        
        # 按创建时间排序
        pending_tasks.sort(key=lambda t: t.created_at)
        
        # 找到目标任务的位置
        for idx, task in enumerate(pending_tasks, start=1):
            if task.task_id == task_id:
                return idx
        
        return 1  # 默认返回 1

    async def _process_queue(self):
        """后台处理循环"""
        while True:
            try:
                request = await self.queue.get()
                request.status = TaskStatus.PROCESSING
                logger.info(f"Processing task: {request.task_id}")

                # 在线程池中运行阻塞的任务
                loop = asyncio.get_event_loop()
                try:
                    if request.task_type == TaskType.SUBTITLE:
                        # 字幕生成任务
                        subtitle_path = await loop.run_in_executor(
                            self.executor,
                            self._run_subtitle_generation,
                            request.params
                        )
                        request.result = None  # 字幕任务没有音频输出
                        request.subtitle_path = subtitle_path
                    elif request.task_type == TaskType.TTS:
                        # TTS 生成任务
                        audio_path, subtitle_path = await loop.run_in_executor(
                            self.executor, 
                            self._run_tts_inference, 
                            request
                        )
                        request.result = audio_path
                        request.subtitle_path = subtitle_path
                    else:
                        raise ValueError(f"Unknown task type: {request.task_type}")
                    
                    request.status = TaskStatus.COMPLETED
                    logger.info(f"Task completed: {request.task_id}")
                except Exception as e:
                    logger.error(f"Task failed: {request.task_id} - {e}", exc_info=True)
                    request.error = str(e)
                    request.status = TaskStatus.FAILED
                finally:
                    self.queue.task_done()
                    
                    # 检查队列是否为空，如果为空则释放模型资源
                    if self.queue.empty():
                        await self._release_model_if_idle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in queue processor: {e}", exc_info=True)
                await asyncio.sleep(1) # 防止死循环

    def _run_tts_inference(
        self, 
        request: TaskRequest
    ) -> tuple[str, Optional[str]]:
        """
        实际执行 TTS 推理 (运行在线程池中)
        
        Args:
            request: TaskRequest实例
        
        Returns:
            (audio_path, subtitle_path): 音频文件路径和字幕文件路径(可选)
        """
        tts_engine = request.tts_engine
        engine_version = request.engine_version
        params = request.params
        
        # 根据引擎类型路由到不同的处理逻辑
        if tts_engine == TTSEngine.INDEXTTS:
            return self._run_indextts_inference(request)
        elif tts_engine == TTSEngine.COSYVOICE:
            return self._run_cosyvoice_inference(params)
        else:
            raise ValueError(f"Unsupported TTS engine: {tts_engine}")
    
    def _run_indextts_inference(
        self,
        request: TaskRequest
    ) -> tuple[str, Optional[str]]:
        """
        执行 IndexTTS 推理
        
        Args:
            request: TaskRequest 实例
        
        Returns:
            (audio_path, subtitle_path): 音频文件路径和字幕文件路径(可选)
        """
        version = request.engine_version
        params = request.params
        
        if not version:
            raise ValueError("IndexTTS engine requires 'engine_version' parameter (V1.5 or V2.0)")
        # 智能模型管理:如果模型版本切换,先卸载旧模型
        if self.current_loaded_version and self.current_loaded_version != version:
            logger.info(f"Model switch detected: {self.current_loaded_version} -> {version}")
            self._unload_model(self.current_loaded_version)
        
        # 懒加载模型
        if version not in self.models:
            self.models[version] = self._load_model(version)
            self.current_loaded_version = version
        
        model = self.models[version]
        
        # 确保 output_path 存在
        if not params.get('output_path'):
            output_dir = "outputs"
            os.makedirs(output_dir, exist_ok=True)
            params['output_path'] = os.path.join(output_dir, f"{str(uuid.uuid4())}.wav")

        logger.info(f"Running inference for {version} with params: {params.keys()}")

        try:
            # --- 文本智能分段与分步合成逻辑 ---
            import re
            import soundfile as sf
            import numpy as np
            import torch
            
            original_text = params['text']
            
            # 分段算法（按换行和标点切分，最大约 300 字左右）
            def chunk_text(text: str, max_chars: int = 300):
                paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
                chunks = []
                for p in paragraphs:
                    if len(p) <= max_chars:
                        chunks.append(p)
                    else:
                        sentences = re.split(r'(?<=[。！？；!?])', p)
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
                                    sub_sentences = re.split(r'(?<=[，、,])', sentence)
                                    sub_chunk = ""
                                    for sub_s in sub_sentences:
                                        if not sub_s.strip(): continue
                                        if len(sub_chunk) + len(sub_s) <= max_chars:
                                            sub_chunk += sub_s
                                        else:
                                            if sub_chunk: chunks.append(sub_chunk)
                                            sub_chunk = sub_s
                                    current_chunk = sub_chunk
                                else:
                                    current_chunk = sentence
                        if current_chunk:
                            chunks.append(current_chunk)
                return [c for c in chunks if c.strip()]

            text_chunks = chunk_text(original_text)
            logger.info(f"Text split into {len(text_chunks)} chunks to prevent VRAM overflow.")
            
            # 在任务实例上注册总分段数量
            if hasattr(request, 'total_chunks'):
                request.total_chunks = len(text_chunks)
            
            output_path = params['output_path']
            temp_files = []
            
            try:
                for idx, chunk in enumerate(text_chunks):
                    logger.info(f"Processing chunk {idx+1}/{len(text_chunks)}: {chunk[:20]}...")
                    if hasattr(request, 'current_chunk'):
                        request.current_chunk = idx + 1
                    
                    # 生成临时音频文件路径
                    chunk_output = output_path.replace(".wav", f"_chunk_{idx}.wav")
                    temp_files.append(chunk_output)
                    
                    if version == "V1.5":
                        infer_params = params.copy()
                        infer_params['text'] = chunk
                        if 'spk_audio_prompt' in infer_params:
                            infer_params['audio_prompt'] = infer_params.pop('spk_audio_prompt')
                        valid_keys = ['text', 'audio_prompt', 'output_path', 'verbose', 'max_text_tokens_per_segment']
                        call_kwargs = {k: v for k, v in infer_params.items() if k in valid_keys}
                        extra_kwargs = {k: v for k, v in infer_params.items() if k not in valid_keys and k in [
                            'top_k', 'top_p', 'temperature', 'do_sample', 'length_penalty', 'repetition_penalty', 'num_beams', 'max_mel_tokens'
                        ]}
                        call_kwargs.update(extra_kwargs)
                        call_kwargs['output_path'] = chunk_output
                        model.infer(**call_kwargs)
                        
                    elif version == "V2.0":
                        infer_params = params.copy()
                        infer_params['text'] = chunk
                        # 动态指定 emotion 文本，防止送入 qwen 的文本过长发生显存溢出
                        if infer_params.get('use_emo_text', False) and not infer_params.get('emo_text'):
                            infer_params['emo_text'] = chunk
                            
                        valid_keys = [
                            'spk_audio_prompt', 'text', 'output_path', 
                            'emo_audio_prompt', 'emo_alpha', 'emo_vector', 
                            'use_emo_text', 'emo_text', 'use_random', 
                            'interval_silence', 'verbose', 'max_text_tokens_per_segment'
                        ]
                        call_kwargs = {k: v for k, v in infer_params.items() if k in valid_keys}
                        extra_kwargs = {k: v for k, v in infer_params.items() if k not in valid_keys and k in [
                            'top_k', 'top_p', 'temperature', 'do_sample', 'length_penalty', 'repetition_penalty', 'num_beams', 'max_mel_tokens'
                        ]}
                        call_kwargs.update(extra_kwargs)
                        call_kwargs['output_path'] = chunk_output
                        
                        if hasattr(model, 'infer'):
                            model.infer(**call_kwargs)
                        else:
                            raise RuntimeError(f"Model {version} has no 'infer' method")
                    else:
                        raise ValueError(f"Unsupported version: {version}")
                        
                    # 主动清理显存，防止在长文本任务中途溢出
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        
                # 所有分段生成完毕后，合并音频
                logger.info(f"Merging {len(temp_files)} audio chunks into final output...")
                combined_audio = []
                sample_rate = 22050
                
                for fpath in temp_files:
                    if os.path.exists(fpath):
                        audio_data, sr = sf.read(fpath)
                        sample_rate = sr
                        combined_audio.append(audio_data)
                        
                        # 增加段落间隔静音 (从 params 获取 interval_silence, 默认 200 ms)
                        interval_ms = params.get('interval_silence', 200)
                        if interval_ms > 0:
                            silence = np.zeros(int(sr * interval_ms / 1000.0), dtype=audio_data.dtype)
                            combined_audio.append(silence)
                            
                # 去除最后多余的一段静音并拼接
                if params.get('interval_silence', 200) > 0 and len(combined_audio) > 1:
                    combined_audio.pop()
                    
                if combined_audio:
                    # 使用 np.concatenate 并在写入时保持原采样格式
                    final_audio = np.concatenate(combined_audio)
                    sf.write(output_path, final_audio, sample_rate, subtype='PCM_16')
                else:
                    raise RuntimeError("No audio chunks generated or read successfully.")
                    
            finally:
                # 清理临时文件
                for fpath in temp_files:
                    if os.path.exists(fpath):
                        try:
                            # 释放文件占用
                            os.remove(fpath)
                        except Exception as e:
                            logger.warning(f"Failed to remove temp file {fpath}: {e}")
            
            # 生成字幕 (如果需要)
            subtitle_path = self._generate_subtitle_if_needed(params, output_path)
            
            return output_path, subtitle_path

        except Exception as e:
            logger.error(f"IndexTTS inference failed: {e}", exc_info=True)
            raise e
    
    def _run_cosyvoice_inference(self, params: Dict[str, Any]) -> tuple[str, Optional[str]]:
        """
        执行 CosyVoice 推理
        
        Args:
            params: 推理参数
        
        Returns:
            (audio_path, subtitle_path): 音频文件路径和字幕文件路径(可选)
        """
        # TODO: 实现 CosyVoice 推理逻辑
        raise NotImplementedError("CosyVoice engine is not yet implemented")

    def _load_model(self, version: str):
        """加载模型实例"""
        logger.info(f"Loading model for version: {version}")
        try:
            from app.utils.yaml_config_loader import yaml_config_loader
            import os
            import importlib
            
            # 使用全局配置加载器实例
            config = yaml_config_loader
            
            # 获取 models_root (相对于项目根目录)
            project_root = os.getcwd()
            models_root_rel = config.get('tts.paths.models_root', 'models')
            models_root = os.path.join(project_root, models_root_rel)

            # 使用属性访问获取版本配置
            tts_config = config.data.get('tts', {})
            versions_config = tts_config.get('versions', {})
            version_config = versions_config.get(version)
            
            if not version_config:
                raise ValueError(f"Unknown version: {version}")
                
            module_name = version_config['module']
            class_name = version_config['class_name']
            model_dir_rel = version_config['model_dir']
            
            # 完整模型目录
            model_dir = os.path.join(models_root, model_dir_rel) # IndexTTS-2 等通常在 models 目录下
            # 或者 model_dir_rel 就是 "IndexTTS-1.5"，且位于 models_root 下
            # 如果 config.yaml 中 model_dir 是相对于 models_root 的
            
            # 修正: config.yaml 通常定义 model_dir 为 "IndexTTS-1.5"
            # 实际路径是 models/IndexTTS-1.5
            full_model_dir = os.path.join(models_root, os.path.basename(model_dir_rel))
            
            # 配置文件路径 - 添加调试信息
            logger.info(f"version_config type: {type(version_config)}")
            logger.info(f"version_config content: {version_config}")
            
            # 安全获取 config_file，处理可能的 _AttrDict 类型
            if hasattr(version_config, 'get'):
                config_file_name = version_config.get('config_file')
            elif isinstance(version_config, dict):
                config_file_name = version_config.get('config_file')
            else:
                config_file_name = None
                
            # 确保是字符串类型
            if not isinstance(config_file_name, str):
                config_file_name = 'config.yaml'
            full_config_path = os.path.join(full_model_dir, config_file_name)

            logger.info(f"Instantiating {class_name} from {module_name}")
            logger.info(f"Model Dir: {full_model_dir}")
            logger.info(f"Config Path: {full_config_path}")

            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            
            # 实例化
            if version == "V1.5":
                # IndexTTS(cfg_path, model_dir, use_fp16, device, use_cuda_kernel)
                instance = cls(
                    cfg_path=full_config_path,
                    model_dir=full_model_dir,
                    use_fp16=True,
                    device="cuda" # 强制使用 cuda，如果可用
                )
            elif version == "V2.0":
                # IndexTTS2(cfg_path, model_dir, use_fp16, device, ...)
                instance = cls(
                    cfg_path=full_config_path,
                    model_dir=full_model_dir,
                    use_fp16=True,
                    device="cuda"
                )
            else:
                 instance = cls() # Fallback

            return instance
        except Exception as e:
            logger.error(f"Failed to load model {version}: {e}", exc_info=True)
            raise e

    def _unload_model(self, version: str):
        """卸载指定版本的模型并释放资源"""
        if version not in self.models:
            return
        
        logger.info(f"Unloading model: {version}")
        model = self.models[version]
        
        try:
            # 调用模型的资源释放方法（如果存在）
            if hasattr(model, 'release_resources'):
                model.release_resources()
            else:
                # 如果没有 release_resources 方法，尝试基本的清理
                import torch
                import gc
                
                # 将模型移到 CPU
                if hasattr(model, 'to'):
                    try:
                        model.to('cpu')
                    except:
                        pass
                
                # 清理 CUDA 缓存
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
                
                gc.collect()
            
            # 从缓存中移除
            del self.models[version]
            logger.info(f"Model {version} unloaded successfully")
            
        except Exception as e:
            logger.error(f"Error unloading model {version}: {e}", exc_info=True)

    async def _release_model_if_idle(self):
        """当队列为空时释放当前加载的模型"""
        if not self.current_loaded_version:
            return
        
        # 等待一小段时间,确保没有新任务进来
        await asyncio.sleep(1)
        
        # 再次检查队列是否仍然为空
        if self.queue.empty():
            logger.info(f"Queue is idle, releasing models...")
            
            # 释放 TTS 模型
            self._unload_model(self.current_loaded_version)
            self.current_loaded_version = None
            
            # 释放 Whisper 模型
            try:
                from app.core.subtitle.whisper_manager import WhisperManager
                whisper_manager = WhisperManager()
                if whisper_manager.model is not None:
                    logger.info("Releasing Whisper model...")
                    whisper_manager.release_resources()
            except Exception as e:
                logger.error(f"Error releasing Whisper model: {e}")
    
    def _generate_subtitle_if_needed(self, params: Dict[str, Any], audio_path: str) -> Optional[str]:
        """
        根据参数决定是否生成字幕
        
        Args:
            params: 请求参数
            audio_path: 音频文件路径
            
        Returns:
            字幕文件路径,如果不需要生成则返回 None
        """
        # 检查是否需要生成字幕
        if not params.get('generate_subtitle', False):
            return None
        
        try:
            logger.info("Generating subtitle...")
            from app.core.subtitle.subtitle_generator import SubtitleGenerator
            
            # 生成字幕文件路径
            subtitle_path = audio_path.replace('.wav', '.srt')
            
            # 创建字幕生成器并生成字幕
            subtitle_generator = SubtitleGenerator()
            subtitle_generator.generate(
                audio_path=audio_path,
                original_text=params['text'],
                output_srt_path=subtitle_path
            )
            
            logger.info(f"Subtitle generated: {subtitle_path}")
            return subtitle_path
            
        except Exception as e:
            logger.error(f"Subtitle generation failed: {e}", exc_info=True)
            # 字幕生成失败不影响主流程,返回 None
            return None
    
    def _run_subtitle_generation(self, params: Dict[str, Any]) -> str:
        """
        执行字幕生成任务 (运行在线程池中)
        
        Args:
            params: 任务参数
                - audio_path: 音频文件路径
                - text: 文本内容
                - output_path: 输出字幕文件路径
        
        Returns:
            subtitle_path: 生成的字幕文件路径
        """
        try:
            logger.info("Starting subtitle generation task...")
            from app.core.subtitle.subtitle_generator import SubtitleGenerator
            
            audio_path = params['audio_path']
            text = params['text']
            output_path = params['output_path']
            
            # 创建字幕生成器并生成字幕
            subtitle_generator = SubtitleGenerator()
            subtitle_path = subtitle_generator.generate(
                audio_path=audio_path,
                original_text=text,
                output_srt_path=output_path
            )
            
            logger.info(f"Subtitle generation completed: {subtitle_path}")
            
            # 注意：音频文件保存在任务目录中，会随任务目录一起被清理，无需手动删除
            
            return subtitle_path
            
        except Exception as e:
            logger.error(f"Subtitle generation task failed: {e}", exc_info=True)
            raise e

