"""
TTS音频生成核心类
封装IndexTTS2的调用逻辑,支持多种情感控制模式
"""

from typing import Optional, Dict, List
from pathlib import Path
import logging
import importlib 

# 注意: torch 和 gc 改为延迟导入，以便在API模式下不依赖本地算力库

from src.common.yaml_config_loader import yaml_config_loader
from src.common.setting import setting

logger = logging.getLogger(__name__)


class TTSGenerator:
    """TTS音频生成器核心类"""
    
    def __init__(self):
        """
        初始化TTS生成器
        
        Args:
            config_path: 应用配置文件路径
        """
        self.config = yaml_config_loader.get("tts", {})
        self.tts = None
        self._initialized = False
        self.use_api = False
    
    def initialize(self) -> bool:
        """初始化TTS模型(根据当前设置的版本)"""
        if self._initialized:
            logger.info("TTS模型已初始化 (Lazy check passed)")
            return True
            
        # 1. Check API Mode
        self.use_api = setting.get(setting.ttsUseAPI)
        if self.use_api:
            logger.info("API 模式已启用，跳过本地模型加载")
            self._initialized = True
            return True
            
        try:
            # 2. 获取当前版本设置
            version = setting.get(setting.ttsVersion)
            logger.info(f"正在初始化TTS模型, 版本: {version}")
            
            # 2. 获取版本配置
            versions_config = self.config.get('versions', {})
            version_config = versions_config.get(version)
            
            if not version_config:
                logger.error(f"未找到版本 {version} 的配置信息")
                return False
            
            # 获取通用模型根目录
            paths_config = self.config.get('paths', {})
            models_root = Path(paths_config.get('models_root', 'models'))
                
            module_name = version_config.get('module')
            class_name = version_config.get('class_name')
            
            # 处理模型路径: 如果是相对路径，则相对于 models_root
            raw_model_dir = version_config.get('model_dir')
            model_dir = Path(raw_model_dir)
            if not model_dir.is_absolute():
                model_dir = models_root / model_dir
                
            # 使用 get_raw_value 获取原始字符串，避免 YamlConfigLoader 自动解析 .yaml 文件内容
            config_file_name = yaml_config_loader.get_raw_value(f'tts.versions.{version}.config_file', 'config.yaml')
            
            logger.info(f"DEBUG: version_config={version_config}")
            logger.info(f"DEBUG: config_file_name type={type(config_file_name)}, value={config_file_name}")
            
            config_file = model_dir / config_file_name
            
            # 3. 验证路径
            if not model_dir.is_dir():
                logger.error(f"模型目录不存在: {model_dir}")
                return False
            
            if not config_file.is_file():
                logger.error(f"模型配置文件不存在: {config_file}")
                return False
                
            # 4. 动态导入模型类
            logger.info(f"导入模型类: {module_name}.{class_name}")
            module = importlib.import_module(module_name)
            ModelClass = getattr(module, class_name)
            
            # 5. 准备初始化参数
            model_config = self.config.get('model', {})
            runtime_settings = model_config.get('runtime_settings', {})
            use_fp16 = setting.get(setting.ttsFP16)
            
            init_kwargs = {
                'cfg_path': str(config_file),
                'model_dir': str(model_dir),
                'use_fp16': use_fp16,
                'use_cuda_kernel': runtime_settings.get('use_cuda_kernel', False)
            }
            
            # V2.0 特有参数
            if version == "V2.0" or class_name == "IndexTTS2":
                init_kwargs['use_deepspeed'] = runtime_settings.get('use_deepspeed', False)
                init_kwargs['models_root'] = str(models_root)
            
            # 6. 实例化模型
            logger.info(f"正在实例化 {class_name}...")
            self.tts = ModelClass(**init_kwargs)
            
            self._initialized = True
            logger.info("TTS模型初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"TTS模型初始化失败: {e}", exc_info=True)
            self._initialized = False # 确保标志位复位
            return False

    def unload(self):
        """卸载模型并释放资源"""
        if self.use_api:
             self.use_api = False
             self._initialized = False
             return

        if self.tts:
            # 尝试调用模型自身的资源释放方法
            if hasattr(self.tts, 'release_resources'):
                try:
                    self.tts.release_resources()
                except Exception as e:
                    logger.error(f"释放模型资源失败: {e}")
            
            del self.tts
            self.tts = None
        
        self._initialized = False
        
        self._initialized = False
        
        # 清理显存
        import torch
        import gc
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        logger.info("TTS模型已卸载，资源已释放")

    def reload(self) -> bool:
        """重载TTS模型(用于切换版本或设置)"""
        logger.info("正在重载TTS模型...")
        # 1. 释放现有资源
        self.unload()
        
        # 2. 检查配置：如果开启了"生成后卸载"，则不立即重新加载，改为懒加载
        model_config = self.config.get('model', {})
        runtime_settings = model_config.get('runtime_settings', {})
        if runtime_settings.get('unload_after_gen', False):
            logger.info("检测到'生成后卸载'配置开启，跳过立即重载，将在下次生成时初始化")
            return True
            
        # 3. 重新初始化
        return self.initialize()
    
    def generate(self, 
                 text: str,
                 spk_audio_prompt: str,
                 output_path: str,
                 emotion_mode: str = "original",
                 emo_audio_prompt: Optional[str] = None,
                 emo_alpha: float = 1.0,
                 emo_vector: Optional[List[float]] = None,
                 emo_text: Optional[str] = None,
                 use_emo_text: bool = False,
                 use_random: bool = False,
                 verbose: bool = True,
                 use_chunking: bool = False,
                 progress_callback: Optional[callable] = None) -> bool:
        """
        生成音频
        ...
        Args:
            progress_callback: 进度回调函数 fn(progress: int, status: str)
        ...
        """
        # 确保模型已初始化
        if not self._initialized:
            if progress_callback:
                progress_callback(5, "正在初始化模型...")
            if not self.initialize():
                return False
        
        try:
            # 验证参数
            if progress_callback:
                progress_callback(10, "正在验证参数...")
            if not self._validate_params(text, spk_audio_prompt, output_path):
                return False
                
            # === API 模式处理 ===
            if self.use_api:
                return self._generate_api(
                    text=text,
                    spk_audio_prompt=spk_audio_prompt, 
                    output_path=output_path,
                    emotion_mode=emotion_mode,
                    emo_audio_prompt=emo_audio_prompt,
                    progress_callback=progress_callback
                )
            
            # 构建infer参数
            
            # 构建infer参数
            infer_params = self._build_infer_params(
                text=text,
                spk_audio_prompt=spk_audio_prompt,
                output_path=output_path,
                emotion_mode=emotion_mode,
                emo_audio_prompt=emo_audio_prompt,
                emo_alpha=emo_alpha,
                emo_vector=emo_vector,
                emo_text=emo_text,
                use_emo_text=use_emo_text,
                use_random=use_random,
                verbose=verbose,
            )
            
            # 临时补丁: 如果 infer_generator 不支持 use_chunking, 我们在这里打印一下
            if use_chunking:
                logger.info("启用了分块生成 (Chunking)")
            
            # 调用IndexTTS2生成音频
            logger.info(f"开始生成音频: {output_path}")
            
            if progress_callback:
                progress_callback(20, "正在生成音频...")
            
            # 迭代生成器并更新进度
            # 注意: 不同模型产生块的数量可能不同，这里做一个简单的进度估算
            generator = self.tts.infer_generator(**infer_params)
            
            # 如果是 V2.0，它可能生成多个块；如果是 V1.5，通常只有一次
            # TODO: 更好的进度估算机制
            try:
                for i, _ in enumerate(generator):
                    if progress_callback:
                        # 假定大约有 5-10 个块，动态更新进度 (20-90%)
                        # 但为了稳健，我们只是发送心跳或简单的增量
                        p = min(20 + (i + 1) * 10, 90)
                        progress_callback(p, f"正在生成音频片段 {i+1}...")
            except Exception as gen_err:
                 logger.error(f"生成过程中出错: {gen_err}")
                 raise gen_err

            logger.info(f"音频生成成功: {output_path}")
            
            if progress_callback:
                progress_callback(95, "正在进行后处理...")
                
            return True
            
        except Exception as e:
            logger.error(f"音频生成失败: {e}", exc_info=True)
            return False
            
        finally:
            # 清理CUDA缓存,防止显存泄漏
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                
            # 检查配置是否需要完全卸载模型
            model_config = self.config.get('model', {})
            runtime_settings = model_config.get('runtime_settings', {})
            if runtime_settings.get('unload_after_gen', False):
                self.unload()
                logger.debug("根据配置已自动释放模型资源")
    
    def _validate_params(self, text: str, spk_audio_prompt: str, output_path: str) -> bool:
        """验证参数"""
        if not text or not text.strip():
            logger.error("文本内容不能为空")
            return False
        
        if not Path(spk_audio_prompt).exists():
            logger.error(f"音色参考音频不存在: {spk_audio_prompt}")
            return False
        
        # 确保输出目录存在
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def _build_infer_params(self, **kwargs) -> Dict:
        """构建IndexTTS2的infer参数"""
        emotion_mode = kwargs.get('emotion_mode', 'original')
        
        # 基础参数
        params = {
            'spk_audio_prompt': kwargs['spk_audio_prompt'],
            'text': kwargs['text'],
            'output_path': kwargs['output_path'],
            'text': kwargs['text'],
            'output_path': kwargs['output_path'],
            'verbose': kwargs.get('verbose', True)
        }
        
        # 处理 chunking 参数
        # if kwargs.get('use_chunking'):
        #    params['use_chunking'] = True
        
        # 根据情感模式添加对应参数
        if emotion_mode == "original":
            # 原音色模式,不添加额外参数
            logger.info("使用原音色模式")
            
        elif emotion_mode == "emo_text":
            # 根据文本生成情感
            logger.info("使用文本生成情感模式")
            params['use_emo_text'] = True
            params['emo_alpha'] = kwargs.get('emo_alpha', 0.6)
            params['use_random'] = kwargs.get('use_random', False)
            
        elif emotion_mode == "reference":
            # 参考情绪音频
            if kwargs.get('emo_audio_prompt'):
                logger.info(f"使用参考音频模式: {kwargs['emo_audio_prompt']}")
                params['emo_audio_prompt'] = kwargs['emo_audio_prompt']
                params['emo_alpha'] = kwargs.get('emo_alpha', 1.0)
            else:
                logger.warning("参考音频模式但未提供音频文件,使用原音色")
                
        elif emotion_mode == "vector":
            # 向量控制
            if kwargs.get('emo_vector'):
                logger.info(f"使用向量控制模式: {kwargs['emo_vector']}")
                params['emo_vector'] = kwargs['emo_vector']
                params['use_random'] = kwargs.get('use_random', False)
            else:
                logger.warning("向量控制模式但未提供向量,使用原音色")
                
        elif emotion_mode == "text":
            # 情感文本描述
            if kwargs.get('emo_text'):
                logger.info(f"使用情感文本描述模式: {kwargs['emo_text']}")
                params['emo_text'] = kwargs['emo_text']
                params['use_emo_text'] = True
                params['emo_alpha'] = kwargs.get('emo_alpha', 0.6)
                params['use_random'] = kwargs.get('use_random', False)
            else:
                logger.warning("情感文本描述模式但未提供文本,使用原音色")
        
        return params
    


    def _generate_api(self, text, spk_audio_prompt, output_path, emotion_mode, emo_audio_prompt, progress_callback):
        """调用远程 API 生成音频"""
        try:
            import requests # Lazy import
            import json
            import os
            
            if progress_callback:
                progress_callback(20, "正在连接 API 服务...")

            api_url = setting.get(setting.ttsAPIAddress)
            api_key = setting.get(setting.ttsAPIKey)
            model_name = setting.get(setting.ttsVersion)
            
            # 简单的参数映射，根据实际 API 协议调整
            payload = {
                "text": text,
                "model": model_name,
                "spk_audio_path": str(spk_audio_prompt), # 这一步可能需要上传文件或传路径，视API而定，这里先假设传路径或Base64
                "emotion": emotion_mode
            }
            
            if emo_audio_prompt:
                 payload["emo_audio_path"] = str(emo_audio_prompt)
            
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            if progress_callback:
                progress_callback(40, "正在请求生成...")
            
            # 发送请求
            # 注意: 这里假设 API 返回的是音频二进制流。
            response = requests.post(f"{api_url}/v1/generate", json=payload, headers=headers, stream=True)
            
            if response.status_code == 200:
                if progress_callback:
                    progress_callback(70, "正在接收音频数据...")
                    
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        
                if progress_callback:
                    progress_callback(100, "生成完成!")
                
                logger.info(f"API 生成成功: {output_path}")
                return True
            else:
                error_msg = f"API 请求失败: {response.status_code} - {response.text}"
                logger.error(error_msg)
                if progress_callback:
                    progress_callback(0, f"失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"API 调用异常: {e}", exc_info=True)
            if progress_callback:
                 progress_callback(0, f"API 错误: {str(e)}")
            return False
    
    def close(self):
        """释放资源"""
        self.tts = None
        self._initialized = False
        
        # 清理CUDA缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("TTS生成器已关闭")

