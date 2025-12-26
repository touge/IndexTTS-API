"""
文件下载路由
提供两种下载方式：流式下载和静态文件访问
"""

import logging
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse
from app.core.queue_manager import QueueManager
from app.core.security import verify_token
from app.utils.yaml_config_loader import yaml_config_loader

logger = logging.getLogger(__name__)
router = APIRouter()

def get_queue_manager():
    raise NotImplementedError

@router.get("/download/{task_id}", tags=["Download"])
async def download_task_result(
    task_id: str,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    """
    流式下载任务生成的音频文件（推荐）
    
    此端点返回文件流，下载后可选择自动删除文件（节省磁盘空间）。
    
    ## 特点
    - ✅ 直接返回文件流，无需额外存储
    - ✅ 下载后可自动删除（根据配置）
    - ✅ 适合一次性下载
    - ⚠️ 下载失败需要重新请求
    
    ## 使用示例
    
    **Python**:
    ```python
    import requests
    
    headers = {"Authorization": "Bearer your-token"}
    
    response = requests.get(
        f"http://localhost:8000/download/{task_id}",
        headers=headers,
        stream=True
    )
    
    with open("output.wav", "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    ```
    
    **cURL**:
    ```bash
    curl -X GET "http://localhost:8000/download/{task_id}" \
      -H "Authorization: Bearer your-token" \
      -o output.wav
    ```
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    
    ## 返回
    - 200: 返回音频文件流（application/octet-stream）
    - 404: 任务不存在或未完成
    - 410: 文件已被删除
    """
    # 获取任务状态
    status = qm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if status["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Task not completed yet. Current status: {status['status']}"
        )
    
    # 直接从任务对象获取文件路径
    task = qm.tasks.get(task_id)
    file_path = task.result if task else None
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail="File has been deleted or not found")
    
    # 获取配置
    delete_after = yaml_config_loader.get('api.output.delete_after_stream', True)
    
    # 返回文件流
    def iterfile():
        with open(file_path, mode="rb") as file_like:
            yield from file_like
        
        # 下载后删除文件（如果配置启用）
        if delete_after:
            try:
                os.remove(file_path)
                # 尝试删除空的任务目录
                task_dir = os.path.dirname(file_path)
                if os.path.exists(task_dir) and not os.listdir(task_dir):
                    os.rmdir(task_dir)
                logger.info(f"File deleted after download: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete file after download: {e}")
    
    filename = os.path.basename(file_path)
    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/files/{task_id}", tags=["Download"])
async def get_task_file(
    task_id: str,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    """
    访问任务生成的音频文件（静态文件方式）
    
    此端点返回静态文件，支持断点续传和多次下载。
    文件会保留一段时间（默认24小时），之后自动清理。
    
    ## 特点
    - ✅ 支持断点续传
    - ✅ 可以多次下载
    - ✅ 适合大文件
    - ✅ 下载失败可以重试
    - ⚠️ 占用磁盘空间
    - ⚠️ 文件会在保留期后自动删除
    
    ## 使用示例
    
    **Python**:
    ```python
    import requests
    
    headers = {"Authorization": "Bearer your-token"}
    
    response = requests.get(
        f"http://localhost:8000/files/{task_id}",
        headers=headers
    )
    
    with open("output.wav", "wb") as f:
        f.write(response.content)
    ```
    
    **浏览器**:
    ```
    http://localhost:8000/files/{task_id}?token=your-token
    ```
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    
    ## 返回
    - 200: 返回音频文件
    - 404: 任务不存在或未完成
    - 410: 文件已被删除
    """
    # 获取任务状态
    status = qm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Task not completed yet. Current status: {status['status']}"
        )
    
    # 直接从任务对象获取文件路径
    task = qm.tasks.get(task_id)
    file_path = task.result if task else None
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail="File has been deleted or not found")
    
    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=filename
    )


@router.get("/download/subtitle/{task_id}", tags=["Download"])
async def download_subtitle(
    task_id: str,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token)
):
    """
    下载任务生成的字幕文件 (SRT 格式)
    
    此端点返回字幕文件流。只有在生成音频时启用了字幕生成功能,
    才会有字幕文件可供下载。
    
    ## 特点
    - ✅ 直接返回字幕文件流
    - ✅ SRT 格式,兼容大多数视频播放器
    - ✅ 下载后可自动删除（根据配置）
    
    ## 使用示例
    
    **Python**:
    ```python
    import requests
    
    headers = {"Authorization": "Bearer your-token"}
    
    response = requests.get(
        f"http://localhost:8000/download/subtitle/{task_id}",
        headers=headers
    )
    
    with open("subtitle.srt", "wb") as f:
        f.write(response.content)
    ```
    
    **cURL**:
    ```bash
    curl -X GET "http://localhost:8000/download/subtitle/{task_id}" \
      -H "Authorization: Bearer your-token" \
      -o subtitle.srt
    ```
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    
    ## 返回
    - 200: 返回字幕文件流（text/plain）
    - 404: 任务不存在、未完成或未生成字幕
    - 410: 文件已被删除
    """
    # 获取任务状态
    status = qm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if status["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Task not completed yet. Current status: {status['status']}"
        )
    
    # 获取字幕文件路径
    task = qm.tasks.get(task_id)
    subtitle_path = task.subtitle_path if task else None
    
    if not subtitle_path:
        raise HTTPException(
            status_code=404,
            detail="Subtitle file not found. The task may not have enabled subtitle generation."
        )
    
    if not os.path.exists(subtitle_path):
        raise HTTPException(status_code=410, detail="Subtitle file has been deleted")
    
    # 获取配置
    delete_after = yaml_config_loader.get('api.output.delete_after_stream', True)
    
    # 返回文件流
    def iterfile():
        with open(subtitle_path, mode="rb") as file_like:
            yield from file_like
        
        # 下载后删除文件（如果配置启用）
        if delete_after:
            try:
                os.remove(subtitle_path)
                logger.info(f"Subtitle file deleted after download: {subtitle_path}")
            except Exception as e:
                logger.warning(f"Failed to delete subtitle file after download: {e}")
    
    filename = os.path.basename(subtitle_path)
    return StreamingResponse(
        iterfile(),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
