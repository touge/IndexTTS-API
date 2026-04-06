import logging
import shutil
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from app.api.schemas import (
    BaseResponse,
    EmotionListResponse,
    EmotionData,
    EmotionMetadata,
    EmotionCategory,
    VoiceDeleteRequest,
    VoiceRenameRequest,
    CategoryCreateRequest
)
from pathlib import Path
from app.core.security import verify_token
from app.utils.yaml_config_loader import yaml_config_loader

logger = logging.getLogger(__name__)
router = APIRouter()

upload_config = yaml_config_loader.get('api.upload', {})
ALLOWED_EXTENSIONS = set(upload_config.get('allowed_audio_extensions', ['.wav', '.mp3', '.flac', '.ogg', '.m4a']))
MAX_FILE_SIZE = upload_config.get('max_reference_audio_size', 300) * 1024 * 1024  # MB 转 字节

def _validate_emo_path(p: str) -> None:
    if ".." in p or p.startswith("/") or p.startswith("\\"):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "Invalid path: traversal not allowed", "code": -1}
        )
    if not p.startswith("voices/emo_audios/"):
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "Only voices/emo_audios/ directory is allowed for emotions", "code": -1}
        )

@router.get("/", response_model=EmotionListResponse)
def get_emotions(token: str = Depends(verify_token)):
    """
    获取情绪音列表
    
    返回情绪音列表并按子目录分类聚合。
    获取到的 `path` 字段可直接作为生成请求中的 `emo_audio_prompt`。
    
    ## 认证
    需要 Bearer Token 认证。
    """
    target_dir = Path("voices/emo_audios")
    category_map = {}
    
    # 支持的音频格式
    valid_extensions = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}
    
    if target_dir.exists() and target_dir.is_dir():
        # 预先扫描所有一级目录，确保"空分类"也能被显示
        for item in target_dir.iterdir():
            if item.is_dir():
                category_map[item.name] = []
                
        for file_path in target_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in valid_extensions:
                rel_path = file_path.relative_to(target_dir)
                category = str(rel_path.parent).replace("\\", "/")
                if category == ".":
                    category = "未分类"
                
                system_path = str(file_path).replace("\\", "/")
                
                if category not in category_map:
                    category_map[category] = []
                    
                category_map[category].append(EmotionMetadata(
                    name=file_path.stem,
                    path=system_path
                ))
                
    categories = [
        EmotionCategory(name=c_name, emos=spks) 
        for c_name, spks in category_map.items()
    ]
                
    return EmotionListResponse(data=EmotionData(categories=categories))

@router.post("/category", response_model=BaseResponse)
async def create_emotion_category(
    req: CategoryCreateRequest,
    token: str = Depends(verify_token)
):
    """
    新增空的分类
    """
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"success": False, "error": "分类名称不能为空", "code": -1})
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail={"success": False, "error": "分类名称包含非法字符", "code": -1})
        
    target_path = Path("voices/emo_audios") / name
    if target_path.exists():
        raise HTTPException(status_code=400, detail={"success": False, "error": "该分类已存在", "code": -1})
        
    try:
        target_path.mkdir(parents=True, exist_ok=True)
        return BaseResponse(code=0, message=f"成功创建情绪分类 {name}")
    except Exception as e:
        logger.error(f"创建分类失败 {target_path}: {e}")
        raise HTTPException(status_code=500, detail={"success": False, "error": f"创建分类失败: {str(e)}", "code": -1})

@router.delete("/", response_model=BaseResponse)
async def delete_emotion(
    req: VoiceDeleteRequest, 
    token: str = Depends(verify_token)
):
    """
    删除情绪音音频或整个分类文件夹
    
    提供相对路径，如 'voices/emo_audios/emotion.wav'。
    """
    path_to_delete = req.path.replace("\\", "/")
    _validate_emo_path(path_to_delete)
    
    target_path = Path(path_to_delete)
    if not target_path.exists():
        raise HTTPException(status_code=404, detail={"success": False, "error": "File or Directory not found", "code": -1})
        
    try:
        if target_path.is_file():
            target_path.unlink()
            logger.info(f"Deleted emotion file: {target_path}")
        elif target_path.is_dir():
            # 判断目录内是否还有音频文件
            audio_files = [
                f for f in target_path.rglob("*")
                if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
            ]
            if audio_files:
                raise HTTPException(
                    status_code=400,
                    detail={"error": f"无法删除分类 '{target_path.name}'，因为该目录下还有 {len(audio_files)} 个音频文件。请先将其清空或移走。", "code": -1}
                )
            shutil.rmtree(target_path)
            logger.info(f"Deleted empty emotion directory: {target_path}")
            
        return BaseResponse(code=0, message=f"情绪音或目录删除成功 ({target_path})")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete {target_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": f"Failed to delete: {str(e)}", "code": -1}
        )

@router.put("/rename", response_model=BaseResponse)
async def rename_emotion(
    req: VoiceRenameRequest, 
    token: str = Depends(verify_token)
):
    """
    重命名情绪音文件或移动分类（重命名文件夹）
    
    提供旧的路径和新的路径，如从 'voices/emo_audios/old.wav' 到 'voices/emo_audios/new.wav'。
    """
    old_p = req.old_path.replace("\\", "/")
    new_p = req.new_path.replace("\\", "/")
    
    _validate_emo_path(old_p)
    _validate_emo_path(new_p)
    
    old_path = Path(old_p)
    new_path = Path(new_p)
    
    if not old_path.exists():
        raise HTTPException(status_code=404, detail={"success": False, "error": "Source not found", "code": -1})
        
    # 防止重命名时产生同名的情绪音
    if old_path.is_file() and old_path.stem != new_path.stem:
        base_dir = Path("voices/emo_audios")
        for existing_file in base_dir.rglob("*"):
            if existing_file.is_file() and existing_file.stem == new_path.stem:
                raise HTTPException(
                    status_code=400, 
                    detail={"success": False, "error": f"名称 '{new_path.stem}' 的情绪音已存在于 '{existing_file.parent.name}' 分类下。为确保情绪音名称唯一不冲突，请更换名称。", "code": -1}
                )
    
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)
        logger.info(f"Renamed emotion from {old_path} to {new_path}")
        
        return BaseResponse(code=0, message=f"情绪音重命名成功 ({new_path.name})")
    except Exception as e:
        logger.error(f"Failed to rename from {old_path} to {new_path}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": f"Failed to rename: {str(e)}", "code": -1}
        )

@router.post("/upload", response_model=BaseResponse)
async def upload_emotion(
    file: UploadFile = File(...),
    category: str = Form(..., description="分类名称，如：开心"),
    name: str = Form(..., description="情绪音名称，如：大笑。这会成为最终的文件名展示"),
    token: str = Depends(verify_token)
):
    """
    上传情绪音音频
    """
    category = category.strip()
    name = name.strip()
    
    if not category or not name:
        raise HTTPException(status_code=400, detail={"success": False, "error": "分类或名称不能为空", "code": -1})
        
    # 路径安全检查
    for field in [category, name]:
        if ".." in field or "/" in field or "\\" in field:
            raise HTTPException(status_code=400, detail={"success": False, "error": "分类或名称中包含非法字符", "code": -1})
            
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
         raise HTTPException(status_code=400, detail={"success": False, "error": f"不支持的音频格式", "code": -1})
         
    base_dir = Path("voices/emo_audios")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    full_path = base_dir / category / f"{name}{file_ext}"
    
    # 检查整个 voices/emo_audios 目录下是否已经存在同名的情绪音（防冲突）
    for existing_file in base_dir.rglob("*"):
        if existing_file.is_file() and existing_file.stem == name:
            # 允许覆盖完全相同路径的文件
            if existing_file.resolve() != full_path.resolve():
                raise HTTPException(
                    status_code=400, 
                    detail={"success": False, "error": f"名称 '{name}' 的情绪音已存在于 '{existing_file.parent.name}' 分类下。为确保情绪音名称唯一不冲突，请更换名称。", "code": -1}
                )
         
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail={"success": False, "error": "文件过大", "code": -1})
        
    with full_path.open("wb") as buffer:
        buffer.write(content)
        
    # 返回相对路径以供展示或直接使用
    rel_path_str = str(full_path).replace("\\", "/")
    return BaseResponse(code=0, message=f"情绪音上传成功 ({name})")
