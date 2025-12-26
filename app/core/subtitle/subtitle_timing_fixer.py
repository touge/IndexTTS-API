# -*- coding: utf-8 -*-
"""
字幕时间轴优化器

消除相邻字幕之间的时间间隙,实现无缝衔接。
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class SubtitleTimingFixer:
    """
    字幕时间轴优化器
    
    通过将相邻字幕间的空白时间平均分配给前后两段,
    消除间隙,提升观看体验。
    """
    
    @staticmethod
    def fix_gaps(aligned_data: List[Dict]) -> List[Dict]:
        """
        修复对齐后的字幕数据中的时间间隙
        
        算法:
        1. 遍历相邻字幕对
        2. 计算时间间隙 = 下一段开始时间 - 当前段结束时间
        3. 如果存在间隙,将间隙的一半补偿给前一段,一半补偿给后一段
        
        Args:
            aligned_data: 对齐后的字幕数据列表,每个元素包含:
                {
                    "text": "文本内容",
                    "start": 起始时间 (秒),
                    "end": 结束时间 (秒)
                }
        
        Returns:
            优化后的字幕数据列表
        """
        if not aligned_data or len(aligned_data) < 2:
            logger.debug("No gaps to fix (less than 2 segments)")
            return aligned_data
        
        logger.info("Starting subtitle gap fixing process...")
        
        gap_count = 0
        total_gap_time = 0.0
        
        # 遍历除最后一个元素外的所有字幕段落
        for i in range(len(aligned_data) - 1):
            current_segment = aligned_data[i]
            next_segment = aligned_data[i + 1]
            
            # 计算当前段落结束和下一段落开始之间的时间间隙
            gap = next_segment['start'] - current_segment['end']
            
            # 如果存在正向的时间间隙
            if gap > 0:
                half_gap = gap / 2
                
                # 记录原始时间
                original_end = current_segment['end']
                original_next_start = next_segment['start']
                
                # 调整时间:当前段落向后延长,下一段落向前提前
                current_segment['end'] += half_gap
                next_segment['start'] -= half_gap
                
                gap_count += 1
                total_gap_time += gap
                
                logger.debug(
                    f"Fixed gap between segment {i} and {i+1}: "
                    f"gap={gap:.3f}s, "
                    f"segment {i} end: {original_end:.3f}s -> {current_segment['end']:.3f}s, "
                    f"segment {i+1} start: {original_next_start:.3f}s -> {next_segment['start']:.3f}s"
                )
        
        logger.info(
            f"Gap fixing complete: fixed {gap_count} gaps, "
            f"total gap time: {total_gap_time:.3f}s"
        )
        
        return aligned_data
