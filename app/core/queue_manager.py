import asyncio
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

@dataclass
class TTSRequest:
    task_id: str
    version: str  # "V1.5" or "V2.0"
    params: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    subtitle_path: Optional[str] = None  # 字幕文件路径
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

class QueueManager:
    def __init__(self):
        # 使用 asyncio.Queue 对协程友好，但在 Worker 线程中实际上我们可能需要一个线程安全的队列
        # 或者我们简单地使用 ThreadPoolExecutor 来运行阻塞的 TTS 任务
        self.queue = asyncio.Queue()
        self.tasks: Dict[str, TTSRequest] = {}
        self.worker_task = None
        self.executor = ThreadPoolExecutor(max_workers=1) # TTS 生成通常是显存密集型，限制为 1 个并发
        self.models = {} # 缓存模型实例
        self.current_loaded_version = None  # 当前加载的模型版本
        
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

    async def submit_task(self, version: str, params: Dict[str, Any]) -> str:
        """提交一个新的 TTS 任务"""
        task_id = str(uuid.uuid4())
        
        # 强制设置输出路径到 tasks 目录（忽略用户提供的 output_path）
        from app.utils.yaml_config_loader import yaml_config_loader
        import os
        
        tasks_dir = yaml_config_loader.get('api.output.tasks_dir', 'output/tasks')
        task_output_dir = os.path.join(tasks_dir, task_id)
        os.makedirs(task_output_dir, exist_ok=True)
        
        params['output_path'] = os.path.join(task_output_dir, f"{task_id}.wav")
        logger.info(f"Output path set to: {params['output_path']}")
        
        request = TTSRequest(task_id=task_id, version=version, params=params)
        self.tasks[task_id] = request
        await self.queue.put(request)
        logger.info(f"Task submitted: {task_id} (Version: {version})")
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
        
        return {
            # 顶层基础信息
            "task_id": task.task_id,
            "status": task.status.value,
            "created_at": created_at_str,
            
            # 详细信息
            "details": {
                "error": task.error,
                "queue_position": queue_position,
                "queue_size": queue_size,
                "created_timestamp": task.created_at,
                "download_url": download_url,
                "file_url": file_url,
                "subtitle_url": subtitle_url
            }
        }
    
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

                # 在线程池中运行阻塞的 TTS 生成
                loop = asyncio.get_event_loop()
                try:
                    audio_path, subtitle_path = await loop.run_in_executor(
                        self.executor, 
                        self._run_inference, 
                        request.version, 
                        request.params
                    )
                    request.result = audio_path
                    request.subtitle_path = subtitle_path
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

    def _run_inference(self, version: str, params: Dict[str, Any]) -> tuple[str, Optional[str]]:
        """
        实际执行推理 (运行在线程池中)
        
        Returns:
            (audio_path, subtitle_path): 音频文件路径和字幕文件路径(可选)
        """
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
            import os
            output_dir = "outputs"
            os.makedirs(output_dir, exist_ok=True)
            params['output_path'] = os.path.join(output_dir, f"{str(uuid.uuid4())}.wav")

        logger.info(f"Running inference for {version} with params: {params.keys()}")

        try:
            output_path = None
            
            if version == "V1.5":
                # V1.5 use infer wrapper
                # 适配参数: spk_audio_prompt -> audio_prompt
                infer_params = params.copy()
                if 'spk_audio_prompt' in infer_params:
                    infer_params['audio_prompt'] = infer_params.pop('spk_audio_prompt')
                
                # 过滤不必要的参数
                valid_keys = ['text', 'audio_prompt', 'output_path', 'verbose', 'max_text_tokens_per_segment']
                call_kwargs = {k: v for k, v in infer_params.items() if k in valid_keys}
                
                # 将其他参数放入 generation_kwargs
                extra_kwargs = {k: v for k, v in infer_params.items() if k not in valid_keys and k in [
                    'top_k', 'top_p', 'temperature', 'do_sample', 'length_penalty', 'repetition_penalty', 'num_beams', 'max_mel_tokens'
                ]}
                call_kwargs.update(extra_kwargs)
                
                output_path = model.infer(**call_kwargs)

            elif version == "V2.0":
                # V2.0 Inference: infer(spk_audio_prompt, text, output_path, ...)
                valid_keys = [
                    'spk_audio_prompt', 'text', 'output_path', 
                    'emo_audio_prompt', 'emo_alpha', 'emo_vector', 
                    'use_emo_text', 'emo_text', 'use_random', 
                    'interval_silence', 'verbose', 'max_text_tokens_per_segment'
                ]
                call_kwargs = {k: v for k, v in params.items() if k in valid_keys}
                
                # Extra generation kwargs
                extra_kwargs = {k: v for k, v in params.items() if k not in valid_keys and k in [
                    'top_k', 'top_p', 'temperature', 'do_sample', 'length_penalty', 'repetition_penalty', 'num_beams', 'max_mel_tokens'
                ]}
                call_kwargs.update(extra_kwargs)

                if hasattr(model, 'infer'):
                    model.infer(**call_kwargs)
                else:
                    raise RuntimeError(f"Model {version} has no 'infer' method")
                
                output_path = params['output_path']
            else:
                raise ValueError(f"Unsupported version: {version}")
            
            # 生成字幕 (如果需要)
            subtitle_path = self._generate_subtitle_if_needed(params, output_path)
            
            return output_path, subtitle_path

        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            raise e

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

