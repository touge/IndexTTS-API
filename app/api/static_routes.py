import logging
from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/voices/{file_path:path}")
async def serve_voice_file(file_path: str):
    """
    提供静态声音文件访问，以供前端播放
    """
    if ".." in file_path or file_path.startswith("/") or file_path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")

    target_path = Path("voices") / file_path

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(target_path),
        media_type="audio/wav",
        headers={"Content-Disposition": "inline"}
    )


@router.get("/{task_id}/{filename}")
async def serve_task_file(task_id: str, filename: str):
    """
    直接访问任务目录下的文件（音频/字幕）。
    GET /static/{task_id}/{task_id}.wav
    GET /static/{task_id}/{task_id}.srt
    纯文件服务，不删文件，不做任务状态校验。
    """
    tasks_dir = Path("tasks")
    file_path = tasks_dir / task_id / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    ext = file_path.suffix.lower()
    media_map = {".wav": "audio/wav", ".srt": "text/plain", ".mp3": "audio/mpeg"}
    return FileResponse(
        path=str(file_path),
        media_type=media_map.get(ext, "application/octet-stream"),
        filename=filename,
    )
