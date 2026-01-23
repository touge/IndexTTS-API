"""
音频文件上传路由
用于客户端上传参考音频和情感音频
"""

import logging
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from app.core.security import verify_token
from app.utils.yaml_config_loader import yaml_config_loader

logger = logging.getLogger(__name__)
router = APIRouter()

# 从配置文件读取文件上传限制
upload_config = yaml_config_loader.get('api.upload', {})
ALLOWED_EXTENSIONS = set(upload_config.get('allowed_audio_extensions', ['.wav', '.mp3', '.flac', '.ogg', '.m4a']))
MAX_FILE_SIZE = upload_config.get('max_reference_audio_size', 300) * 1024 * 1024  # MB 转 字节

@router.post("/upload/audio", tags=["Upload"])
async def upload_audio(
    file: UploadFile = File(...),
    path: str = Form(...),
    token: str = Depends(verify_token)
):
    """
    上传音频文件到服务器
    
    用于上传参考音频和情感音频文件，以便服务器在生成时使用。
    
    ## 请求参数
    
    - **file**: 音频文件（二进制）
    - **path**: 服务器端保存路径，如 `voices/ref_audios/speaker.wav`
    
    ## 支持的音频格式
    
    - WAV (.wav)
    - MP3 (.mp3)
    - FLAC (.flac)
    - OGG (.ogg)
    - M4A (.m4a)
    
    ## 使用示例
    
    **Python**:
    ```python
    import requests
    
    headers = {"Authorization": "Bearer your-token"}
    
    with open("speaker.wav", "rb") as f:
        files = {"file": f}
        data = {"path": "voices/ref_audios/speaker.wav"}
        
        response = requests.post(
            "http://localhost:8000/upload/audio",
            headers=headers,
            files=files,
            data=data
        )
    
    print(response.json())
    # {"success": true, "path": "voices/ref_audios/speaker.wav"}
    ```
    
    **cURL**:
    ```bash
    curl -X POST "http://localhost:8000/upload/audio" \
      -H "Authorization: Bearer your-token" \
      -F "file=@speaker.wav" \
      -F "path=voices/ref_audios/speaker.wav"
    ```
    
    ## 返回
    
    **成功（200 OK）**:
    ```json
    {
        "success": true,
        "path": "voices/ref_audios/speaker.wav"
    }
    ```
    
    **失败（400 Bad Request）**:
    ```json
    {
        "success": false,
        "error": "Invalid file format"
    }
    ```
    
    ## 注意事项
    
    - 文件大小限制：50MB
    - 如果文件已存在，将被覆盖
    - 路径会自动创建所需的目录
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    """
    try:
        # 验证路径安全性（防止路径遍历攻击）
        if ".." in path or path.startswith("/") or path.startswith("\\"):
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "Invalid path: path traversal not allowed"
                }
            )
        
        # 验证文件扩展名
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": f"Invalid file format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                }
            )
        
        # 构建完整路径
        full_path = Path(path)
        
        # 创建目录
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 读取文件内容并检查大小
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": f"文件过大。最大限制: {upload_config.get('max_reference_audio_size', 300)}MB"
                }
            )
        
        # 保存文件
        with full_path.open("wb") as buffer:
            buffer.write(content)
        
        logger.info(f"Audio file uploaded: {path} ({len(content)} bytes)")
        
        return {
            "success": True,
            "path": path,
            "size": len(content)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload audio file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e)
            }
        )
