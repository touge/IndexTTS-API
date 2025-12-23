# IndexTTS API 测试配置
# ==========================================
# 提示：
# 1. 带有 [必填] 标记的参数必须提供
# 2. 带有 [可选] 标记的参数可以删除或注释掉，将使用默认值
# 3. 建议仅在需要调整效果时修改 [可选] 参数
# ==========================================

spk_audio_prompt = "voices/ref_audios/常用/ref_1766279369751.wav"
text = "一颗火星大小的行星。以每秒十五公里的速度。狠狠撞上了原始地球。那瞬间的能量，超过万亿颗原子弹。撞击掀起的尘埃和岩石。在引力作用下，凝聚成了今天的月球。"

#魔魔
spk_audio_prompt = "voices/ref_audios/男声/ref_1766276899769.wav"

# ==========================================
# V1.5 测试配置
# ==========================================
TEST_PAYLOAD_V1_5 = {
    # --- [必填] 核心参数 ---
    "text": text,              # 要合成的文本
    "spk_audio_prompt": spk_audio_prompt, # 参考音频文件名 (需位于服务器可访问路径)
    
    # --- [可选] 输出设置 ---
    "output_path": "output/v1_5.wav",            # 输出文件名 (默认自动生成)
    
    # --- [可选] 生成控制参数 (默认值已在下方备注) ---
    # "top_k": 30,                           # 采样 Top-K (默认: 30)
    # "top_p": 0.8,                          # 采样 Top-P (默认: 0.8)
    # "temperature": 1.0,                    # 温度参数 (默认: 1.0)
    "top_k": 30,                             # 示例：覆盖默认值
    "temperature": 0.8,                     # 示例：覆盖默认值
    
    # "repetition_penalty": 10.0,            # 重复惩罚 (默认: 10.0)
    "repetition_penalty": 10.0,               # 示例：覆盖默认值
    
    # "max_text_tokens_per_segment": 120,    # 分句最大 Token 数 (默认: 120)
    "max_text_tokens_per_segment": 120,      # 示例：覆盖默认值
    
    # "max_mel_tokens": 600,                 # 最大生成 Mel 长度 (默认: 600)
    "max_mel_tokens": 600,                   # 示例：覆盖默认值
    
    # --- [可选] 高级生成参数 ---
    # "do_sample": True,                     # 是否采样 (默认: True)
    "do_sample": True,                      # 示例：关闭采样
    # "num_beams": 3,                        # Beam Search 数量 (默认: 3)
    "num_beams": 3,                          # 示例：覆盖默认值
    "verbose": True                          # 是否打印详细日志
}

# ==========================================
# V2.0 测试配置
# ==========================================
TEST_PAYLOAD_V2_0 = {
    # --- [必填] 核心参数 ---
    "text": text,              # 要合成的文本
    "spk_audio_prompt": spk_audio_prompt, # 参考音频文件名
    
    # --- [可选] 输出设置 ---
    "output_path": "output/v2_0.wav",            # 输出文件名
    
    # --- [可选] 情感控制参数 (重点关注) ---
    # 注意：以下情感控制方式通常只选其一，或组合使用
    
    # 方式A: 使用情感参考音频
    # "emo_audio_prompt": "emo_ref.wav",       # 情感参考音频路径
    
    # 方式B: 使用文本提取情感
    "use_emo_text": False,                    # 开启文本情感提取 (默认: False)
    # "emo_text": "Sad text",                  # 用于提取情感的文本 (如果不填则使用 source text)
    
    # 方式C: 直接指定情感向量 (高级)
    "emo_vector": None, #[0.1, ...],              # 必须与模型情感维度一致 (默认: None)
    # "emo_vector": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], # 示例向量
    
    # 通用情感混合比例
    "emo_alpha": 1.0,                      # 情感强度 0.0 ~ 1.0+ (默认: 1.0)
    # "emo_alpha": 0.7,                        # 示例：降低情感强度
    
    # "use_random": False,                   # 是否使用随机情感 (默认: False)
    
    # --- [可选] 其他控制 ---
    "interval_silence": 200,               # 句间静音 ms (默认: 200)
    # "interval_silence": 300,                 # 示例：覆盖默认值
    
    # --- [可选] 生成控制参数 (V2.0 默认值) ---
    # "temperature": 0.8,                    # V2.0 默认温度为 0.8
    # "temperature": 0.75,                     # 示例：覆盖默认值
    # "top_k": 30,
    # "top_k": 40,
    # "max_mel_tokens": 1500,                # V2.0 支持更长生成 (默认: 1500)
    # "max_mel_tokens": 1000
    
    # 其他未列出的参数将使用 schemas.py 中的默认值
}
