import logging
from fastapi import APIRouter, HTTPException, Depends
from app.api.schemas import TTSRequestV1_5, TaskSubmitResponse, TaskStatusResponse, TaskSubmitData
from app.core.queue_manager import QueueManager, TaskType, TTSEngine
from app.core.security import verify_token
from app.core.audio_utils import resolve_audio_prompt

from pathlib import Path
logger = logging.getLogger(__name__)
router = APIRouter()

# 获取 QueueManager 实例的依赖项 (将在 main.py 中注入)
def get_queue_manager():
    # 这是一个占位符，实际在主应用中会覆盖此依赖
    raise NotImplementedError

@router.post("/generate", response_model=TaskSubmitResponse)
async def generate_v1_5(
    request: TTSRequestV1_5,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)  # 添加 Token 认证
):
    """
    提交 IndexTTS V1.5 生成任务
    
    V1.5 是基础版本，简单稳定，不支持情感控制。
    适合基础的音色克隆和 TTS 需求。
    
    ## 基础示例
    ```json
    {
        "text": "这是要合成的文本内容",
        "speaker": "张三"
    }
    ```
    
    ## 完整示例（包含可选参数）
    ```json
    {
        "text": "这是要合成的文本内容",  // 必填
        "speaker": "voices/speaker.wav",  // 必填
        "output_path": "output/result.wav",  // 可选，不填则自动生成
        
        // 以下为可选的生成控制参数
        "top_k": 30,  // 可选，Top-K 采样，默认30
        "temperature": 1.0,  // 可选，温度参数，默认1.0
        "repetition_penalty": 10.0,  // 可选，重复惩罚，默认10.0
        "max_mel_tokens": 600,  // 可选，最大生成长度，默认600
        "max_text_tokens_per_segment": 120,  // 可选，分段大小，默认120
        
        "do_sample": true,  // 可选，是否采样，默认true
        "num_beams": 3,  // 可选，Beam Search，默认3
        "verbose": false,  // 可选，详细日志，默认false
        
        "generate_subtitle": true  // 可选，是否生成字幕文件，默认false
    }
    ```
    
    ## 核心参数
    - **text** (必填): 要合成的文本
    - **speaker** (必填): 参考发音人 (名称或路径)
    - **output_path** (可选): 输出文件路径
    
    ## 生成控制参数（全部可选）
    - **top_k** (默认30): Top-K 采样，控制生成多样性
    - **temperature** (默认1.0): 温度参数，值越高越随机
    - **repetition_penalty** (默认10.0): 重复惩罚，防止重复内容
    - **max_mel_tokens** (默认600): 最大生成长度
    - **max_text_tokens_per_segment** (默认120): 文本分段大小
    - **do_sample** (默认true): 是否启用采样
    - **num_beams** (默认3): Beam Search 束宽
    - **verbose** (默认false): 是否打印详细日志
    - **generate_subtitle** (默认false): 是否生成字幕文件 (SRT 格式)
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    
    ## 返回
    返回任务ID，可通过 /status/{task_id} 查询任务状态
    """
    try:
        # 将 Pydantic 模型转换为字典参数
        params = request.model_dump(exclude_none=True)
        
        # 打印用户请求参数（用于调试）
        logger.info(f"V1.5 Request payload: {params}")
        
        # 转换参数适配底层引擎
        if 'speaker' in params:
            params['spk_audio_prompt'] = params.pop('speaker')
            
        # 解析音频路径（支持短名称）
        if 'spk_audio_prompt' in params:
            params['spk_audio_prompt'] = resolve_audio_prompt(params['spk_audio_prompt'])
            
        # 检查音频文件是否存在
        required_files = [params.get('spk_audio_prompt')]
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
        
        task_id = await qm.submit_task(
            task_type=TaskType.TTS,
            tts_engine=TTSEngine.INDEXTTS,
            engine_version="V1.5",
            params=params
        )
        return TaskSubmitResponse(data=TaskSubmitData(task_id=task_id))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit V1.5 task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


