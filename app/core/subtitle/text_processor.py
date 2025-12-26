# -*- coding: utf-8 -*-
"""
文本处理工具类

提供文本标准化、分句、时间格式化等功能。
"""

import re
import logging
import warnings
from typing import List
from opencc import OpenCC
import cn2an

logger = logging.getLogger(__name__)


class TextProcessor:
    """
    文本处理工具类
    
    功能:
    - 文本标准化 (繁简转换、数字转换、去标点)
    - 句子分割和清洗
    - 时间格式化 (SRT 格式)
    """
    
    def __init__(self):
        """初始化文本处理器"""
        try:
            # 初始化 OpenCC (繁体转简体)
            self.cc = OpenCC('t2s')
            logger.info("TextProcessor initialized with OpenCC")
        except Exception as e:
            logger.error(f"Failed to initialize OpenCC: {e}")
            self.cc = None
    
    def normalize(self, text: str) -> str:
        """
        对文本进行深度规范化
        
        处理步骤:
        1. 繁体转简体
        2. 中文数字转阿拉伯数字
        3. 移除标点,转为小写
        
        Args:
            text: 原始文本
            
        Returns:
            规范化后的文本
        """
        if not text:
            return ""
        
        # Step 1: 繁体转简体
        if self.cc:
            try:
                simplified_text = self.cc.convert(text)
            except Exception as e:
                logger.warning(f"OpenCC conversion failed: {e}, using original text")
                simplified_text = text
        else:
            simplified_text = text
        
        # Step 2: 中文数字转阿拉伯数字
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            try:
                normalized_text = cn2an.transform(simplified_text, "cn2an")
            except (ValueError, KeyError):
                # 转换失败时回退为简体文本
                normalized_text = simplified_text
        
        # Step 3: 移除非字母数字字符并转小写
        normalized_text = re.sub(r'[^\w]', '', normalized_text).lower()
        
        return normalized_text
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """
        将秒数转为 SRT 字幕格式 (HH:MM:SS,毫秒)
        
        Args:
            seconds: 秒数 (浮点数)
            
        Returns:
            SRT 格式时间字符串,如 "00:01:23,456"
        """
        if seconds < 0:
            logger.warning(f"Negative seconds value: {seconds}, using 0")
            seconds = 0
        
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        
        # 格式化为 "HH:MM:SS,ms"
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"
    
    @staticmethod
    def split_and_clean_sentences(text: str) -> List[str]:
        """
        拆分文本为句子,去除多余标点和空串
        
        处理步骤:
        1. 按句子尾部的中文/英文标点进行分割
        2. 清理每句末尾标点
        3. 去除空句子
        
        Args:
            text: 原始文本
            
        Returns:
            句子列表
        """
        if not text:
            return []
        
        # 使用正则按句子尾部的标点进行分割
        # 使用负向回顾断言避免在数字和小数点之间分割
        sentences = re.split(r'(?<=[，、。？：；,.:;?!])(?<!\d\.)(?!\d)', text)
        
        cleaned_sentences = []
        for sentence in sentences:
            s = sentence.strip()
            if s:
                # 去掉句尾多余标点
                s = re.sub(r'[，、。？：；,.:;?!]+$', '', s)
                if s:  # 再次检查是否为空
                    cleaned_sentences.append(s)
        
        logger.debug(f"Split text into {len(cleaned_sentences)} sentences")
        return cleaned_sentences
    
    @staticmethod
    def smart_split(text: str, min_len: int = 5, max_len: int = 20) -> List[str]:
        """
        智能拆分句子为多个短句
        
        保证每段长度在 [min_len, max_len] 之间,
        优先在标点、词语边界处断开。
        
        Args:
            text: 待拆分文本
            min_len: 最小长度
            max_len: 最大长度
            
        Returns:
            拆分后的短句列表
        """
        if len(text) <= max_len:
            return [text]
        
        punctuation_breaks = ['，', '。', '？', '；', '：', ',', '.', '?', ';', ':']
        result = []
        start = 0
        
        while start < len(text):
            # 查找合适断点 (从 max_len 往回找,优先标点)
            end = min(len(text), start + max_len)
            found = False
            
            for i in range(end, start + min_len - 1, -1):
                if text[i - 1] in punctuation_breaks:
                    result.append(text[start:i].strip())
                    start = i
                    found = True
                    break
            
            if not found:
                # 没有标点断点,硬切
                result.append(text[start:end].strip())
                start = end
        
        # 过滤掉过短片段
        result = [s for s in result if len(s) >= min_len]
        
        logger.debug(f"Smart split text into {len(result)} segments")
        return result
