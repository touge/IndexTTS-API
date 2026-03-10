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
    # 验证 file_path 防止路径遍历
    if ".." in file_path or file_path.startswith("/") or file_path.startswith("\\"):
         raise HTTPException(status_code=400, detail="Invalid path")

    target_path = Path("voices") / file_path

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(target_path),
        media_type="audio/wav", # 默认假设类型
        headers={"Content-Disposition": "inline"}
    )
