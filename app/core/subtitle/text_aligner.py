# -*- coding: utf-8 -*-
"""
文本-音频对齐器

使用模糊匹配算法将原始文本与 Whisper 转录结果对齐。
"""

import logging
from typing import List, Dict, Set, Tuple
from tqdm import tqdm
from thefuzz import fuzz
from opencc import OpenCC

logger = logging.getLogger(__name__)


class TextAligner:
    """
    文本-音频对齐器
    
    使用滑动窗口和模糊匹配算法,将原始文本句子与
    Whisper 转录的词序列进行对齐,获取每句话的时间轴。
    """
    
    def __init__(self, text_processor, match_threshold: int = 75):
        """
        初始化对齐器
        
        Args:
            text_processor: TextProcessor 实例
            match_threshold: 模糊匹配阈值 (0-100)
        """
        self.text_processor = text_processor
        self.match_threshold = match_threshold
        self.cc = OpenCC('t2s')  # 繁体转简体
    
    def linear_align(
        self,
        target_lines: List[str],
        whisper_words: List[Dict],
        search_window_multiplier: int = 3,
        debug: bool = False
    ) -> Tuple[List[Dict], Set[int]]:
        """
        线性对齐算法
        
        使用滑动窗口在 Whisper 转录词序列中搜索每个目标句子,
        找到最佳匹配的音频片段。
        
        Args:
            target_lines: 目标文本句子列表
            whisper_words: Whisper 转录的词列表,每个词包含 {"word": "词", "start": 0.0, "end": 0.5}
            search_window_multiplier: 搜索窗口大小倍数
            debug: 是否输出调试信息
            
        Returns:
            (aligned_results, used_word_indices)
            - aligned_results: 对齐结果列表,每个元素包含:
                {
                    "text": 原始文本,
                    "start": 起始时间,
                    "end": 结束时间
                }
            - used_word_indices: 已使用的词索引集合
        """
        aligned_results = []
        used_word_indices = set()
        whisper_idx = 0  # 当前搜索起始索引
        
        for line in tqdm(target_lines, desc="Aligning text to audio"):
            # 标准化目标文本
            normalized_line = self.text_processor.normalize(line)
            if not normalized_line:
                logger.debug(f"Skipping empty line after normalization: '{line}'")
                continue
            
            # 定义搜索窗口
            search_start_idx = whisper_idx
            max_search_words = 150
            search_window_size = min(
                len(normalized_line) * search_window_multiplier + 20,
                max_search_words
            )
            search_end_idx = min(search_start_idx + search_window_size, len(whisper_words))
            
            if search_start_idx >= len(whisper_words):
                if debug:
                    logger.debug(f"No more whisper words to search for line: '{line}'")
                continue
            
            best_score = -1
            best_match_info = None
            
            # 双层循环穷举所有可能的子序列
            for i in range(search_start_idx, search_end_idx):
                for j in range(i, search_end_idx):
                    sub_sequence = whisper_words[i:j+1]
                    if not sub_sequence:
                        continue
                    
                    # 拼接子序列文本
                    sub_sequence_text = "".join([w['word'] for w in sub_sequence])
                    normalized_sub_sequence = self.text_processor.normalize(sub_sequence_text)
                    
                    # 繁体转简体 (Whisper 可能输出繁体)
                    try:
                        simplified_sub_sequence = self.cc.convert(normalized_sub_sequence)
                    except Exception as e:
                        logger.warning(f"OpenCC conversion failed: {e}")
                        simplified_sub_sequence = normalized_sub_sequence
                    
                    # 计算模糊匹配得分
                    current_score = fuzz.token_set_ratio(normalized_line, simplified_sub_sequence)
                    
                    # 更新最佳匹配
                    if current_score > best_score:
                        best_score = current_score
                        best_match_info = {
                            "words": sub_sequence,
                            "start_idx": i,
                            "end_idx": j + 1
                        }
            
            # 检查是否找到有效匹配
            if best_score >= self.match_threshold and best_match_info:
                aligned_results.append({
                    "text": line,
                    "start": best_match_info['words'][0]['start'],
                    "end": best_match_info['words'][-1]['end']
                })
                
                # 更新搜索起点
                whisper_idx = best_match_info['end_idx']
                
                # 标记已使用的词索引
                for k in range(best_match_info['start_idx'], best_match_info['end_idx']):
                    used_word_indices.add(k)
                
                if debug:
                    logger.debug(
                        f"Matched '{line}' with score {best_score}, "
                        f"time: {best_match_info['words'][0]['start']:.2f}s - "
                        f"{best_match_info['words'][-1]['end']:.2f}s"
                    )
            else:
                # 匹配失败,滑动窗口
                logger.warning(
                    f"Failed to match line '{line}' (best score: {best_score}), "
                    f"threshold: {self.match_threshold}"
                )
                whisper_idx += max(1, len(normalized_line) // 2)
                whisper_idx = min(whisper_idx, len(whisper_words))
        
        logger.info(
            f"Alignment complete: {len(aligned_results)}/{len(target_lines)} lines matched"
        )
        
        return aligned_results, used_word_indices
