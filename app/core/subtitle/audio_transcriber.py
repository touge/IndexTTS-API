# -*- coding: utf-8 -*-
"""
音频转录器

封装 Whisper 模型的音频转录功能,提取词级时间戳。
"""

import logging
from typing import Dict, List, Optional, Tuple
from tqdm import tqdm

logger = logging.getLogger(__name__)


class AudioTranscriber:
    """
    音频转录器
    
    使用 Whisper 模型转录音频,提取词级时间戳信息。
    """
    
    def __init__(self, whisper_manager):
        """
        初始化音频转录器
        
        Args:
            whisper_manager: WhisperManager 实例
        """
        self.whisper_manager = whisper_manager
    
    def transcribe(
        self,
        audio_file: str,
        beam_size: int = 5,
        word_timestamps: bool = True
    ) -> Tuple[str, List[Dict], Optional[Dict]]:
        """
        转录音频文件
        
        Args:
            audio_file: 音频文件路径
            beam_size: Beam search 大小
            word_timestamps: 是否启用词级时间戳
            
        Returns:
            (full_text, segments_info, info)
            - full_text: 完整转录文本
            - segments_info: 片段信息列表,每个片段包含:
                {
                    "start": 起始时间,
                    "end": 结束时间,
                    "text": 文本内容,
                    "words": 词级信息列表 [{"word": "词", "start": 0.0, "end": 0.5}, ...]
                }
            - info: 转录元数据
        """
        whisper_model = self.whisper_manager.get_model()
        
        if not whisper_model:
            logger.error("Whisper model not available for transcription")
            return "", [], None
        
        logger.info(f"Transcribing audio file: {audio_file} (this may take a while)...")
        
        try:
            # 调用 Whisper 模型进行转录
            segments, info = whisper_model.transcribe(
                audio_file,
                beam_size=beam_size,
                word_timestamps=word_timestamps
            )
            
            full_text = ""
            segments_info = []
            
            # 遍历所有转录片段
            for segment in tqdm(segments, desc="Processing transcription segments"):
                full_text += segment.text
                
                words_info = []
                if segment.words:
                    for word in segment.words:
                        words_info.append({
                            "word": word.word,
                            "start": word.start,
                            "end": word.end
                        })
                
                # 组装片段信息
                segments_info.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "words": words_info
                })
            
            logger.info(f"Audio transcription complete. Transcribed {len(segments_info)} segments")
            return full_text, segments_info, info
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}", exc_info=True)
            raise
