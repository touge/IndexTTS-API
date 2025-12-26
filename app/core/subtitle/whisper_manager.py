# -*- coding: utf-8 -*-
"""
Whisper 模型管理器

负责 Whisper 模型的加载、管理和资源释放。
采用单例模式,全局共享一个模型实例。
"""

import logging
import os
from typing import Optional
import torch
import gc

logger = logging.getLogger(__name__)


class WhisperManager:
    """
    Whisper 模型管理器 (单例模式)
    
    负责:
    - 按需加载 Whisper 模型
    - 提供模型实例访问
    - 释放模型资源
    """
    
    _instance: Optional['WhisperManager'] = None
    _model = None
    _model_path: Optional[str] = None
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化管理器"""
        # 单例模式下,只初始化一次
        if not hasattr(self, '_initialized'):
            self._initialized = True
            logger.info("WhisperManager initialized")
    
    def load_model(self, model_path: str, device: str = "auto", compute_type: str = "float16"):
        """
        加载 Whisper 模型
        
        Args:
            model_path: 模型路径
            device: 设备 ("auto", "cuda", "cpu")
            compute_type: 计算类型 ("float16", "int8", "float32")
        """
        # 如果模型已加载且路径相同,直接返回
        if self._model is not None and self._model_path == model_path:
            logger.info(f"Whisper model already loaded from {model_path}")
            return self._model
        
        # 如果模型已加载但路径不同,先释放旧模型
        if self._model is not None:
            logger.info(f"Unloading previous Whisper model from {self._model_path}")
            self.release_resources()
        
        try:
            from faster_whisper import WhisperModel
            
            logger.info(f"Loading Whisper model from {model_path}...")
            
            # 检查模型路径是否存在
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Whisper model not found at {model_path}")
            
            # 加载模型
            self._model = WhisperModel(
                model_path,
                device=device,
                compute_type=compute_type
            )
            self._model_path = model_path
            
            logger.info(f"Whisper model loaded successfully from {model_path}")
            return self._model
            
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
            raise
    
    def get_model(self):
        """
        获取当前加载的模型实例
        
        Returns:
            WhisperModel 实例,如果未加载则返回 None
        """
        return self._model
    
    @property
    def model(self):
        """模型实例属性"""
        return self._model
    
    def release_resources(self):
        """
        释放 Whisper 模型资源
        
        与 TTS 模型的 release_resources() 方法保持一致
        """
        if self._model is None:
            logger.debug("No Whisper model to release")
            return
        
        logger.info("Releasing Whisper model resources...")
        
        try:
            # 删除模型引用
            del self._model
            self._model = None
            self._model_path = None
            
            # 清理 CUDA 缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            
            # 强制垃圾回收
            gc.collect()
            
            logger.info("Whisper model resources released successfully")
            
        except Exception as e:
            logger.error(f"Error releasing Whisper model resources: {e}", exc_info=True)
