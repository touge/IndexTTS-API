"""
字幕生成路由
用于上传音频和文本文档生成字幕
"""

import logging
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import Optional
from app.api.schemas import SubtitleGenerationResponse
from app.core.queue_manager import QueueManager, TaskType
from app.core.security import verify_token
from app.utils.yaml_config_loader import yaml_config_loader

logger = logging.getLogger(__name__)
router = APIRouter()

# 从配置文件读取文件上传限制
upload_config = yaml_config_loader.get('api.upload', {})
ALLOWED_AUDIO_EXTENSIONS = set(upload_config.get('allowed_audio_extensions', ['.wav', '.mp3', '.flac', '.ogg', '.m4a']))
ALLOWED_TEXT_EXTENSIONS = set(upload_config.get('allowed_text_extensions', ['.txt', '.md']))
MAX_AUDIO_SIZE = upload_config.get('max_subtitle_audio_size', 1024) * 1024 * 1024  # MB 转 字节
MAX_TEXT_SIZE = upload_config.get('max_text_size', 50) * 1024 * 1024  # MB 转 字节

# 获取 QueueManager 实例的依赖项
def get_queue_manager():
    raise NotImplementedError

@router.post("/generate", response_model=SubtitleGenerationResponse, tags=["Subtitle"])
async def generate_subtitle(
    audio_file: UploadFile = File(..., description="音频文件"),
    text_file: Optional[UploadFile] = File(None, description="文本文档（可选，与 text 参数二选一）"),
    text: Optional[str] = Form(None, description="文本内容（可选，与 text_file 参数二选一）"),
    output_filename: Optional[str] = Form(None, description="输出文件名（可选）"),
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    """
    上传音频和文本文档生成字幕
    
    通过上传音频文件和文本文档（或直接提供文本内容），使用 Whisper 识别音频，
    然后将识别结果与文本进行对齐（以文本为准），生成 SRT 格式的字幕文件。
    
    ## 请求参数
    
    - **audio_file** (必填): 音频文件
    - **text_file** (可选): 文本文档（.txt 格式）
    - **text** (可选): 文本内容（字符串）
    - **output_filename** (可选): 输出字幕文件名
    
    **注意**: `text_file` 和 `text` 参数必须提供其中一个。
    
    ## 支持的音频格式
    
    - WAV (.wav)
    - MP3 (.mp3)
    - FLAC (.flac)
    - OGG (.ogg)
    - M4A (.m4a)
    
    ## 使用示例
    
    **Python (使用文本内容)**:
    ```python
    import requests
    
    headers = {"Authorization": "Bearer your-token"}
    
    with open("audio.wav", "rb") as audio:
        files = {"audio_file": audio}
        data = {"text": "这是要对齐的文本内容"}
        
        response = requests.post(
            "http://localhost:8000/subtitle/generate",
            headers=headers,
            files=files,
            data=data
        )
    
    task_id = response.json()["task_id"]
    print(f"任务已提交: {task_id}")
    ```
    
    **Python (使用文本文档)**:
    ```python
    import requests
    
    headers = {"Authorization": "Bearer your-token"}
    
    with open("audio.wav", "rb") as audio, open("text.txt", "rb") as text_doc:
        files = {
            "audio_file": audio,
            "text_file": text_doc
        }
        
        response = requests.post(
            "http://localhost:8000/subtitle/generate",
            headers=headers,
            files=files
        )
    
    task_id = response.json()["task_id"]
    ```
    
    **cURL**:
    ```bash
    curl -X POST "http://localhost:8000/subtitle/generate" \
      -H "Authorization: Bearer your-token" \
      -F "audio_file=@audio.wav" \
      -F "text=这是要对齐的文本内容"
    ```
    
    ## 返回
    
    返回任务ID，可通过 `/status/{task_id}` 查询任务状态。
    任务完成后，可通过 `subtitle_url` 下载生成的字幕文件。
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    """
    try:
        # 1. 验证音频文件
        audio_ext = Path(audio_file.filename).suffix.lower()
        if audio_ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_audio_format",
                    "message": f"不支持的音频格式。允许的格式: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
                }
            )
        
        # 2. 验证文本输入（必须提供 text 或 text_file 之一）
        if not text and not text_file:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_text_input",
                    "message": "必须提供 text 或 text_file 参数之一"
                }
            )
        
        if text and text_file:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "conflicting_text_input",
                    "message": "不能同时提供 text 和 text_file 参数"
                }
            )
        
        # 3. 读取音频文件
        audio_content = await audio_file.read()
        if len(audio_content) > MAX_AUDIO_SIZE:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "audio_file_too_large",
                    "message": f"音频文件过大。最大限制: {upload_config.get('max_subtitle_audio_size', 1024)}MB"
                }
            )
        
        # 4. 获取文本内容
        text_content = None
        if text_file:
            # 验证文本文件格式
            text_ext = Path(text_file.filename).suffix.lower()
            if text_ext not in ALLOWED_TEXT_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "invalid_text_format",
                        "message": f"不支持的文本格式。允许的格式: {', '.join(ALLOWED_TEXT_EXTENSIONS)}"
                    }
                )
            
            # 读取文本文件
            text_file_content = await text_file.read()
            if len(text_file_content) > MAX_TEXT_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "text_file_too_large",
                        "message": f"文本文件过大。最大限制: {upload_config.get('max_text_size', 50)}MB"
                    }
                )
            
            # 解码文本内容
            try:
                text_content = text_file_content.decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "text_encoding_error",
                        "message": "文本文件必须使用 UTF-8 编码"
                    }
                )
        else:
            text_content = text
        
        # 5. 准备任务参数
        # 注意：音频内容暂存在内存中，将在队列处理时保存到任务目录
        params = {
            "audio_content": audio_content,  # 传递音频二进制内容
            "audio_ext": audio_ext,          # 传递音频扩展名
            "text": text_content,
            "output_filename": output_filename or "subtitle.srt"
        }
        
        # 6. 提交任务到队列
        task_id = await qm.submit_task(
            task_type=TaskType.SUBTITLE,
            params=params
        )
        
        logger.info(f"Subtitle generation task submitted: {task_id}")
        
        return SubtitleGenerationResponse(task_id=task_id)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit subtitle generation task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
