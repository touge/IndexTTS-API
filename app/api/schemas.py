# -*- coding: utf-8 -*-
"""
IndexTTS API 数据模型定义
=======================

本文件定义了 IndexTTS API 接口使用的所有数据模型 (Pydantic Models)。
涵盖了通用响应结构、任务提交/查询响应结构，以及 V1.5 和 V2.0 版本的
详细请求参数定义。

主要类:
- BaseResponse: 基础响应格式
- TTSRequestV1_5: V1.5 版本推理参数
- TTSRequestV2_0: V2.0 版本推理参数 (包含情感控制)
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

# 情感控制模式枚举
class EmotionMode(str, Enum):
    """V2.0 情感控制模式"""
    SAME_AS_SPEAKER = "same_as_speaker"  # 与音色参考者音频相同（不使用额外情感控制）
    REFERENCE_AUDIO = "reference_audio"  # 参考音频控制
    EMOTION_VECTOR = "emotion_vector"    # 情绪向量控制（8维向量）
    TEXT_DRIVEN = "text_driven"          # 文本驱动情感提取

# ==========================================
# 响应模型 (Response Models)
# ==========================================

class BaseResponse(BaseModel):
    """
    通用 API 响应基类
    所有 API 响应都应继承或包含此结构。
    """
    status: str = "success"        # 接口状态 (success 或 failed，任务状态使用 pending/completed 等)
    code: int = 0                  # 状态码 (0 表示成功，其他值表示特定的错误类型)
    message: str = "操作成功"       # 状态信息或错误描述文本
    data: Optional[Any] = None     # 响应数据载荷 (可选，通常包含实际的业务数据)

class TaskSubmitData(BaseModel):
    task_id: str                   # 唯一的任务 ID (UUID 格式)，用于后续轮询状态

class TaskSubmitResponse(BaseResponse):
    """
    任务提交成功后的响应模型
    返回任务 ID 供客户端查询进度。
    """
    data: TaskSubmitData

class TaskData(BaseModel):
    """任务详细信息"""
    task_id: str                   # 任务 ID
    created_at: str                # 任务创建时间（人类可读格式，如 "2024-12-23 16:30:00"）
    error: Optional[str] = None           # 错误信息（仅 failed 状态）
    queue_position: Optional[int] = None  # 队列位置 (0=执行中, >=1=排队中, None=已结束)
    queue_size: int = 0                   # 当前队列总大小
    created_timestamp: float = 0.0        # 原始时间戳（用于程序处理）
    download_url: Optional[str] = None    # 流式下载链接（推荐，仅 completed 状态）
    file_url: Optional[str] = None        # 静态文件链接（备用，仅 completed 状态）
    subtitle_url: Optional[str] = None    # 字幕文件下载链接（仅 completed 状态且生成了字幕）

class TaskStatusResponse(BaseResponse):
    """
    任务状态查询接口的响应模型
    
    外层通过 status (pending, processing, completed, failed) 标识任务状态
    任务的全部详细信息统一位于 data 字段中
    """
    data: Optional[TaskData] = None

# ==========================================
# 请求参数模型 (Request Models)
# ==========================================

class TTSRequestV1_5(BaseModel):
    """
    IndexTTS V1.5 版本请求参数
    对应底层模型: IndexTTS (infer.py)
    """
    # --- 核心参数 ---
    text: str = Field(..., description="要合成的文本内容")
    speaker: str = Field(..., description="参考发音人 (可以是完整路径或直接输入名称，如 '老赫氣泡音版')")
    output_path: Optional[str] = Field(None, description="输出文件保存路径。如果不提供，系统将自动生成临时路径。")
    volume: Optional[float] = Field(None, description="音量大小 (0.0 ~ 2.0)，1.0 为原始音量，暂未实现")
    
    # --- 生成控制参数 ---
    # 控制文本分段大小，影响显存占用和生成速度。显存较小时可调小此值。
    max_text_tokens_per_segment: int = 120 
    
    # --- 采样与解码参数 ---
    top_k: int = 30                # Top-K 采样：仅从概率最高的 K 个 token 中采样 (infer.py 默认: 30)
    top_p: float = 0.8             # Top-P (Nucleus) 采样：累积概率阈值 (infer.py 默认: 0.8)
    temperature: float = 1.0       # 温度参数：控制生成的随机性和多样性，值越高越随机 (默认: 1.0)
    
    do_sample: bool = True         # 是否启用采样策略 (True=采样, False=贪婪搜索)
    num_beams: int = 3             # Beam Search 的束宽 (仅在 do_sample=False 时可能作为 fallback 或特定实现生效)
    
    length_penalty: float = 0.0    # 长度惩罚：正值鼓励生成更长的序列，负值鼓励更短的序列
    repetition_penalty: float = 10.0 # 重复惩罚：防止生成重复内容 (默认: 10.0)
    
    max_mel_tokens: int = 600      # 最大生成的 Mel 帧数，直接控制生成音频的最大长度
    verbose: bool = False          # 是否在服务端控制台打印详细的推理日志
    
    # --- 字幕生成控制 ---
    generate_subtitle: bool = Field(False, description="是否生成字幕文件 (SRT 格式)")

class TTSRequestV2_0(BaseModel):
    """
    IndexTTS V2.0 版本请求参数
    对应底层模型: IndexTTS2 (infer_v2.py)
    相比 V1.5，V2.0 增加了丰富的情感和风格控制能力。
    """
    # --- 核心参数 ---
    text: str = Field(..., description="要合成的文本内容")
    speaker: str = Field(..., description="参考发音人 (可以是完整路径或直接输入名称，如 '老赫氣泡音版')")
    output_path: Optional[str] = Field(None, description="输出文件保存路径")
    volume: Optional[float] = Field(None, description="音量大小 (0.0 ~ 2.0)，1.0 为原始音量，暂未实现")
    
    # --- 情感控制模式（可选，仅在 /emo_mode/generate 端点使用） ---
    emotion_mode: Optional[EmotionMode] = Field(None, description="情感控制模式（可选）")
    
    # --- 情感与风格控制参数（根据 emotion_mode 自动使用） ---
    # 1. 情感参考音频：使用另一段音频的情感风格应用到当前合成中
    emotion: Optional[str] = Field(None, description="情感参考音 (可以是完整路径或直接输入名称)。如果不填，默认复用 speaker。")
    
    # 2. 情感混合：控制情感参考音频对最终结果的影响程度
    emo_alpha: float = 1.0         # 情感强度系数 (0.0 ~ 1.0+)。1.0 为标准强度，数值越大情感越强烈。
    
    # 3. 情感向量：直接指定情感的数值向量 (高级用法，需了解模型内部向量定义)
    emo_vector: Optional[List[float]] = Field(None, description="显式指定情感向量 (List[float])，若设置将覆盖其他情感推断设置。")
    
    # 4. 文本提取情感：从 prompt 文本中利用 LLM 自动分析情感
    use_emo_text: bool = False     # 是否开启文本情感提取功能 (需加载 QwenEmotion 模型)
    emo_text: Optional[str] = None # 用于提取情感的具体文本。如果 use_emo_text=True 且此项为空，则默认使用 `text` 参数。
    
    # 5. 随机情感
    use_random: bool = False       # 是否使用随机情感风格 (用于探索性生成)
    
    # 6. 其他控制
    interval_silence: int = 200    # 多段生成时，段落之间的静音时长 (毫秒)
    
    # --- 生成控制参数 (与 V1.5 类似，但默认值可能不同) ---
    max_text_tokens_per_segment: int = 120
    
    top_k: int = 30
    top_p: float = 0.8
    temperature: float = 0.8       # V2.0 默认温度通常较低 (0.8) 以保持声音稳定性
    
    do_sample: bool = True
    num_beams: int = 3
    length_penalty: float = 0.0
    repetition_penalty: float = 10.0
    
    max_mel_tokens: int = 1500     # V2.0 模型通常支持生成更长的序列 (默认: 1500)
    
    verbose: bool = False          # 是否打印详细日志
    
    # --- 字幕生成控制 ---
    generate_subtitle: bool = Field(False, description="是否生成字幕文件 (SRT 格式)")

# ==========================================
# 字幕生成相关模型
# ==========================================

class SubtitleGenerationResponse(BaseResponse):
    """
    字幕生成任务提交响应
    返回任务 ID 供客户端查询进度
    """
    task_id: str  # 任务 ID

# ==========================================
# 发音人列表相关模型
# ==========================================

class SpeakerMetadata(BaseModel):
    """发音人元数据"""
    name: str = Field(..., description="文件名（包含扩展名，如：DV.wav）。你可以直接拿它的无扩展名或全名作为 speaker 参数")
    path: str = Field(..., description="相对路径（作为 speaker 参数的值，如：voices/ref_audios/常用/DV.wav）")

class SpeakerCategory(BaseModel):
    """发音人分类"""
    name: str = Field(..., description="分类名称（对应的文件夹名称，如：常用, 男声, 女声）")
    speakers: List[SpeakerMetadata] = Field(..., description="该分类下的发音人列表")

class SpeakerData(BaseModel):
    categories: List[SpeakerCategory] = Field(..., description="可用发音人分类列表")

class SpeakerListResponse(BaseResponse):
    """
    发音人列表响应模型
    """
    data: SpeakerData

# ==========================================
# 情绪音列表相关模型
# ==========================================

class EmotionMetadata(BaseModel):
    """情绪音元数据"""
    name: str = Field(..., description="文件名（包含扩展名，如：laugh.wav）。你可以直接拿它的无扩展名或全名作为 emotion 参数")
    path: str = Field(..., description="相对路径（作为 emotion 参数的值，如：voices/emo_audios/开心/laugh.wav）")

class EmotionCategory(BaseModel):
    """情绪音分类"""
    name: str = Field(..., description="分类名称（对应的文件夹名称，如：开心, 伤心, 生气）")
    emos: List[EmotionMetadata] = Field(..., description="该分类下的情绪音列表")

class EmotionData(BaseModel):
    categories: List[EmotionCategory] = Field(..., description="可用情绪音分类列表")

class EmotionListResponse(BaseResponse):
    """
    情绪音列表响应模型
    """
    data: EmotionData

class VoiceDeleteRequest(BaseModel):
    """删除语音文件请求"""
    path: str = Field(..., description="要删除的文件的相对路径，如 'voices/ref_audios/speaker.wav'")

class VoiceRenameRequest(BaseModel):
    """重命名语音文件或文件夹请求"""
    old_path: str = Field(..., description="旧路径，如 'voices/ref_audios/old.wav'")
    new_path: str = Field(..., description="新路径，如 'voices/ref_audios/new.wav'")

class CategoryCreateRequest(BaseModel):
    """新建空分类请求"""
    name: str = Field(..., description="要创建的新分类名称")
