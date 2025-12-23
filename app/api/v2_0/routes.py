import logging
from fastapi import APIRouter, HTTPException, Depends
from app.api.schemas import TTSRequestV2_0, TaskSubmitResponse, TaskStatusResponse
from app.core.queue_manager import QueueManager
from app.core.security import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

def get_queue_manager():
    raise NotImplementedError

@router.post("/generate", response_model=TaskSubmitResponse)
async def generate_v2_0(
    request: TTSRequestV2_0,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)  # 添加 Token 认证
):
    """
    提交 IndexTTS V2.0 生成任务（纯参数方式）
    
    此端点直接使用底层参数，完全兼容原项目 vendor/indextts/infer_v2.py
    推荐对外使用，便于跟随原项目升级。
    
    ## 四种情感控制方式
    
    ### 方式1: 与音色参考者音频相同（默认）
    不提供任何情感参数，使用说话人原始情感
    ```json
    {
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav"
    }
    ```
    
    ### 方式2: 参考音频控制
    使用另一段音频的情感作为参考
    ```json
    {
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "emo_audio_prompt": "voices/happy.wav",
        "emo_alpha": 0.8
    }
    ```
    参数说明:
    - emo_audio_prompt: 情感参考音频路径
    - emo_alpha: 情感强度 (0.0-1.0, 默认1.0)
    
    ### 方式3: 情绪向量控制
    使用 8 维向量精确控制情感比例
    ```json
    {
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],
        "emo_alpha": 0.9
    }
    ```
    向量维度: [高兴, 愤怒, 悲伤, 恐惧, 反感, 低落, 惊讶, 自然]
    
    ### 方式4: 文本驱动
    使用 QwenEmotion 模型自动分析文本情感
    ```json
    {
        "text": "今天真是太开心了！",
        "spk_audio_prompt": "voices/speaker.wav",
        "use_emo_text": true
    }
    ```
    或指定单独的情感文本:
    ```json
    {
        "text": "这是要合成的文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "use_emo_text": true,
        "emo_text": "非常高兴和激动"
    }
    ```
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    
    ## 返回
    返回任务ID，可通过 /status/{task_id} 查询任务状态
    """
    try:
        params = request.model_dump(exclude_none=True)
        
        # 移除 emotion_mode 参数（如果用户误传了）
        params.pop('emotion_mode', None)
        
        # 打印用户请求参数（用于调试）
        logger.info(f"V2.0 Request payload: {params}")
        
        # 检查音频文件是否存在
        from pathlib import Path
        required_files = [params.get('spk_audio_prompt')]
        if params.get('emo_audio_prompt'):
            required_files.append(params['emo_audio_prompt'])
        
        missing_files = []
        for file_path in required_files:
            if file_path and not Path(file_path).exists():
                missing_files.append(file_path)
        
        # 如果有缺失文件，返回错误
        if missing_files:
            logger.warning(f"Missing audio files: {missing_files}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_audio_files",
                    "message": "Required audio files not found on server",
                    "missing_files": missing_files
                }
            )
        
        # 记录使用的情感控制方式
        if params.get('emo_vector'):
            logger.info(f"Using emotion vector control: {params['emo_vector']}")
        elif params.get('use_emo_text'):
            logger.info(f"Using text-driven emotion: {params.get('emo_text', 'using main text')}")
        elif params.get('emo_audio_prompt'):
            logger.info(f"Using reference audio control: {params['emo_audio_prompt']}")
        else:
            logger.info("Using speaker's original emotion (no additional control)")
        
        task_id = await qm.submit_task(version="V2.0", params=params)
        return TaskSubmitResponse(task_id=task_id)
    except Exception as e:
        logger.error(f"Failed to submit V2.0 task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emo_mode/generate", response_model=TaskSubmitResponse)
async def generate_v2_0_with_emo_mode(
    request: TTSRequestV2_0,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)  # 添加 Token 认证
):
    """
    提交 IndexTTS V2.0 生成任务（emotion_mode 简化方式）
    
    此端点使用 emotion_mode 枚举参数简化配置，适合内部工具使用。
    系统会根据 emotion_mode 自动设置底层参数。
    
    ## 四种 emotion_mode 模式
    
    ### 模式1: same_as_speaker（与音色相同）
    不使用额外情感控制，使用说话人原始情感
    ```json
    {
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "emotion_mode": "same_as_speaker"
    }
    ```
    
    ### 模式2: reference_audio（参考音频）
    使用另一段音频的情感作为参考
    ```json
    {
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "emotion_mode": "reference_audio",
        "emo_audio_prompt": "voices/happy.wav",  // 必填
        "emo_alpha": 0.8  // 可选，默认1.0
    }
    ```
    **必填参数**: emo_audio_prompt  
    **可选参数**: emo_alpha (情感强度，0.0-1.0)
    
    ### 模式3: emotion_vector（情绪向量）
    使用 8 维向量精确控制情感
    ```json
    {
        "text": "这是测试文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "emotion_mode": "emotion_vector",
        "emo_vector": [0.7, 0.0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0],  // 必填，8维
        "emo_alpha": 0.9  // 可选，默认1.0
    }
    ```
    **必填参数**: emo_vector (8维列表)  
    **可选参数**: emo_alpha (整体强度缩放)  
    **向量维度**: [高兴, 愤怒, 悲伤, 恐惧, 反感, 低落, 惊讶, 自然]
    
    ### 模式4: text_driven（文本驱动）
    自动分析文本情感
    ```json
    {
        "text": "今天真是太开心了！",
        "spk_audio_prompt": "voices/speaker.wav",
        "emotion_mode": "text_driven"
        // emo_text 可选，不填则使用 text
    }
    ```
    或指定单独的情感文本:
    ```json
    {
        "text": "这是要合成的文本",
        "spk_audio_prompt": "voices/speaker.wav",
        "emotion_mode": "text_driven",
        "emo_text": "非常高兴和激动"  // 可选
    }
    ```
    **可选参数**: emo_text (不填则使用主文本)
    
    ## 参数验证
    - reference_audio 模式必须提供 emo_audio_prompt，否则返回 400 错误
    - emotion_vector 模式必须提供 8 维 emo_vector，否则返回 400 错误
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    
    ## 返回
    返回任务ID，可通过 /status/{task_id} 查询任务状态
    """
    try:
        params = request.model_dump(exclude_none=True)
        
        # 打印用户请求参数（用于调试）
        logger.info(f"V2.0 emo_mode Request payload: {params}")
        
        # 检查音频文件是否存在（在处理 emotion_mode 之前）
        from pathlib import Path
        required_files = [params.get('spk_audio_prompt')]
        if params.get('emo_audio_prompt'):
            required_files.append(params['emo_audio_prompt'])
        
        missing_files = []
        for file_path in required_files:
            if file_path and not Path(file_path).exists():
                missing_files.append(file_path)
        
        # 如果有缺失文件，返回错误
        if missing_files:
            logger.warning(f"Missing audio files: {missing_files}")
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_audio_files",
                    "message": "Required audio files not found on server",
                    "missing_files": missing_files
                }
            )
        
        # 根据 emotion_mode 自动设置情感控制参数
        emotion_mode = params.get('emotion_mode', 'same_as_speaker')
        
        if emotion_mode == 'same_as_speaker':
            # 与音色参考者音频相同：不使用额外情感控制
            params['emo_audio_prompt'] = None
            params['use_emo_text'] = False
            params['emo_vector'] = None
            logger.info("Emotion mode: SAME_AS_SPEAKER (no additional emotion control)")
            
        elif emotion_mode == 'reference_audio':
            # 参考音频控制：确保 emo_audio_prompt 已设置
            if not params.get('emo_audio_prompt'):
                raise HTTPException(
                    status_code=400, 
                    detail="emotion_mode='reference_audio' requires 'emo_audio_prompt' parameter"
                )
            params['use_emo_text'] = False
            params['emo_vector'] = None
            logger.info(f"Emotion mode: REFERENCE_AUDIO (emo_audio_prompt={params['emo_audio_prompt']})")
            
        elif emotion_mode == 'emotion_vector':
            # 情绪向量控制：确保 emo_vector 已设置
            if not params.get('emo_vector'):
                raise HTTPException(
                    status_code=400,
                    detail="emotion_mode='emotion_vector' requires 'emo_vector' parameter (8-dim list)"
                )
            # 验证向量维度
            if len(params['emo_vector']) != 8:
                raise HTTPException(
                    status_code=400,
                    detail=f"emo_vector must be 8-dimensional, got {len(params['emo_vector'])}"
                )
            params['emo_audio_prompt'] = None
            params['use_emo_text'] = False
            logger.info(f"Emotion mode: EMOTION_VECTOR (vector={params['emo_vector']})")
            
        elif emotion_mode == 'text_driven':
            # 文本驱动：启用文本情感提取
            params['use_emo_text'] = True
            params['emo_audio_prompt'] = None
            params['emo_vector'] = None
            # 如果没有提供 emo_text，使用主文本
            if not params.get('emo_text'):
                params['emo_text'] = params['text']
            logger.info(f"Emotion mode: TEXT_DRIVEN (emo_text={params.get('emo_text', 'using main text')})")
        
        # 移除 emotion_mode 参数（底层模型不需要）
        params.pop('emotion_mode', None)
        
        task_id = await qm.submit_task(version="V2.0", params=params)
        return TaskSubmitResponse(task_id=task_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit V2.0 task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



