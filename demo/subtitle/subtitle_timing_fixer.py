"""
subtitle_timing_fixer.py

该模块提供了一个核心功能：优化字幕数据的时间轴，消除相邻字幕间的空隙。
通过将两段字幕之间的空白时间平均分配给前后两段，实现无缝衔接，提升观看体验。
"""

from typing import List, Dict
from src.logger import log

class SubtitleTimingFixer:
    """
    一个用于修复和优化字幕时间轴的工具类。
    """

    @staticmethod
    def fix_gaps(aligned_data: List[Dict]) -> List[Dict]:
        """
        核心方法：修复对齐后的字幕数据中的时间间隙。

        该方法遍历字幕数据列表，计算相邻两段字幕之间的时间差（gap）。
        如果存在间隙，它会将间隙时长的一半（half_gap）分别补偿给
        前一段字幕的结束时间点和后一段字幕的开始时间点。

        Args:
            aligned_data (List[Dict]): 一个包含字幕信息的列表。
                每个元素是一个字典，至少包含 'start' 和 'end' 两个键，
                值是浮点型的秒数。
                例如: [{'text': '你好', 'start': 0.5, 'end': 1.2}, ...]

        Returns:
            List[Dict]: 经过时间轴优化后的字幕数据列表。
        """
        if not aligned_data or len(aligned_data) < 2:
            return aligned_data

        log.info("--- Starting subtitle gap fixing process ---")
        
        # 遍历除最后一个元素外的所有字幕段落
        for i in range(len(aligned_data) - 1):
            current_segment = aligned_data[i]
            next_segment = aligned_data[i + 1]

            # 计算当前段落结束和下一段落开始之间的时间间隙
            gap = next_segment['start'] - current_segment['end']

            # 如果存在正向的时间间隙
            if gap > 0:
                half_gap = gap / 2
                
                # 记录原始时间以供日志输出
                original_end = current_segment['end']
                original_next_start = next_segment['start']

                # 调整时间：当前段落向后延长，下一段落向前提前
                current_segment['end'] += half_gap
                next_segment['start'] -= half_gap
                
                log.debug(
                    f"Adjusted gap between segment {i} and {i+1}: "
                    f"Gap was {gap:.3f}s. "
                    f"Segment {i} end moved from {original_end:.3f}s to {current_segment['end']:.3f}s. "
                    f"Segment {i+1} start moved from {original_next_start:.3f}s to {next_segment['start']:.3f}s."
                )

        log.success("--- Subtitle gap fixing process completed ---")
        return aligned_data
