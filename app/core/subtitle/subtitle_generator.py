# -*- coding: utf-8 -*-
"""
字幕生成器

整合所有字幕生成模块,提供完整的字幕生成流程。
"""

import os
import logging
from typing import List, Dict, Optional
import yaml

from .whisper_manager import WhisperManager
from .text_processor import TextProcessor
from .audio_transcriber import AudioTranscriber
from .text_aligner import TextAligner
from .subtitle_timing_fixer import SubtitleTimingFixer

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """
    字幕生成器
    
    完整流程:
    1. 分句: 将原始文本分割为句子
    2. 转录: 使用 Whisper 转录音频
    3. 对齐: 将句子与转录结果对齐
    4. 优化: 修复时间轴间隙
    5. 生成: 输出 SRT 文件
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化字幕生成器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.whisper_manager = WhisperManager()
        self.text_processor = TextProcessor()
    
    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            # 返回默认配置
            return {
                'tts': {
                    'paths': {'models_root': 'models'},
                    'subtitle': {
                        'enabled': True,
                        'whisper_model': 'whisper/faster-whisper-large-v2',
                        'whisper_config': {
                            'beam_size': 5,
                            'word_timestamps': True
                        },
                        'alignment': {
                            'match_threshold': 75,
                            'search_window_multiplier': 3
                        }
                    }
                }
            }
    
    def generate(
        self,
        audio_path: str,
        original_text: str,
        output_srt_path: str
    ) -> str:
        """
        生成字幕文件
        
        Args:
            audio_path: 音频文件路径
            original_text: 原始文本
            output_srt_path: 输出 SRT 文件路径
            
        Returns:
            生成的 SRT 文件路径
            
        Raises:
            FileNotFoundError: 音频文件不存在
            RuntimeError: 字幕生成失败
        """
        # 检查音频文件是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        logger.info(f"Starting subtitle generation for {audio_path}")
        
        try:
            # 1. 加载 Whisper 模型
            subtitle_config = self.config.get('tts', {}).get('subtitle', {})
            models_root = self.config.get('tts', {}).get('paths', {}).get('models_root', 'models')
            whisper_model_path = os.path.join(
                models_root,
                subtitle_config.get('whisper_model', 'whisper/faster-whisper-large-v2')
            )
            
            self.whisper_manager.load_model(whisper_model_path)
            
            # 2. 分句
            sentences = self._split_text_into_sentences(original_text)
            logger.info(f"Split text into {len(sentences)} sentences")
            
            # 3. 转录音频
            whisper_config = subtitle_config.get('whisper_config', {})
            whisper_segments = self._transcribe_audio(
                audio_path,
                beam_size=whisper_config.get('beam_size', 5),
                word_timestamps=whisper_config.get('word_timestamps', True)
            )
            logger.info(f"Transcribed audio into {len(whisper_segments)} segments")
            
            # 4. 对齐文本与音频
            alignment_config = subtitle_config.get('alignment', {})
            aligned_data = self._align_text_to_audio(
                sentences,
                whisper_segments,
                match_threshold=alignment_config.get('match_threshold', 75),
                search_window_multiplier=alignment_config.get('search_window_multiplier', 3)
            )
            logger.info(f"Aligned {len(aligned_data)} sentences")
            
            # 5. 优化时间轴
            aligned_data = SubtitleTimingFixer.fix_gaps(aligned_data)
            
            # 6. 生成 SRT 文件
            self._create_srt_file(aligned_data, output_srt_path)
            
            logger.info(f"Subtitle generation complete: {output_srt_path}")
            return output_srt_path
            
        except Exception as e:
            logger.error(f"Subtitle generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Subtitle generation failed: {e}")
    
    def _split_text_into_sentences(self, text: str) -> List[str]:
        """
        拆分文本为句子
        
        处理规则:
        1. 使用 TextProcessor 分句
        2. 合并过短的句子 (≤5字 + 下一句≤15字)
        3. 可选: 拆分过长的句子 (>20字)
        """
        raw_sentences = TextProcessor.split_and_clean_sentences(text)
        
        processed_sentences = []
        i = 0
        
        while i < len(raw_sentences):
            current = raw_sentences[i].strip()
            
            # 合并过短的句子
            if len(current) <= 5 and i + 1 < len(raw_sentences):
                next_line = raw_sentences[i + 1].strip()
                if len(next_line) <= 15:
                    merged = current + ' ' + next_line
                    processed_sentences.append(merged)
                    i += 2
                    continue
            
            # 默认情况:直接添加
            processed_sentences.append(current)
            i += 1
        
        return processed_sentences
    
    def _transcribe_audio(
        self,
        audio_path: str,
        beam_size: int = 5,
        word_timestamps: bool = True
    ) -> List[Dict]:
        """转录音频"""
        audio_transcriber = AudioTranscriber(self.whisper_manager)
        _, whisper_segments, _ = audio_transcriber.transcribe(
            audio_path,
            beam_size=beam_size,
            word_timestamps=word_timestamps
        )
        
        if not whisper_segments:
            raise RuntimeError("Transcription failed, no segments returned")
        
        return whisper_segments
    
    def _align_text_to_audio(
        self,
        sentences: List[str],
        whisper_segments: List[Dict],
        match_threshold: int = 75,
        search_window_multiplier: int = 3
    ) -> List[Dict]:
        """对齐文本与音频"""
        # 提取所有词
        all_whisper_words = []
        for segment in whisper_segments:
            all_whisper_words.extend(segment.get('words', []))
        
        # 执行对齐
        text_aligner = TextAligner(self.text_processor, match_threshold=match_threshold)
        aligned_data, _ = text_aligner.linear_align(
            sentences,
            all_whisper_words,
            search_window_multiplier=search_window_multiplier
        )
        
        return aligned_data
    
    def _create_srt_file(self, aligned_data: List[Dict], output_path: str):
        """生成 SRT 文件"""
        # 按开始时间排序
        aligned_data.sort(key=lambda x: x['start'])
        
        # 写入 SRT 文件
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, entry in enumerate(aligned_data):
                start_time = TextProcessor.format_time(entry['start'])
                end_time = TextProcessor.format_time(entry['end'])
                text = entry['text']
                
                f.write(f"{i + 1}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text.strip()}\n\n")
        
        logger.info(f"SRT file created: {output_path}")
