import os
from pathlib import Path
from typing import Optional

def resolve_audio_prompt(name_or_path: Optional[str]) -> Optional[str]:
    """
    解析音频路径。如果是全路径且存在则直接返回。
    如果只是名字（不包含路径分隔符），则在 voices/ref_audios 或 voices/emo_audios 下查找该名字。
    优先级：全路径存在 > ref_audios中精确匹配带扩展名 > ref_audios中精确匹配不带扩展名。
    """
    if not name_or_path:
        return name_or_path
        
    p = Path(name_or_path)
    if p.exists():
        return name_or_path
        
    # 如果包含路径分隔符但不存在，不再尝试搜索（认为用户传递了特定路径但文件丢失）
    if "/" in name_or_path or "\\" in name_or_path:
        return name_or_path

    # 在 voices/ref_audios 中搜索
    ref_audios_dir = Path("voices/ref_audios")
    if ref_audios_dir.exists():
        # 第一遍：完全匹配文件名（即使用户可能传了扩展名）
        for file_path in ref_audios_dir.rglob("*"):
            if file_path.is_file() and file_path.name == name_or_path:
                return str(file_path).replace("\\", "/")
                
        # 第二遍：匹配 stem (不含扩展名)
        valid_extensions = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}
        for file_path in ref_audios_dir.rglob("*"):
            if file_path.is_file() and file_path.stem == name_or_path and file_path.suffix.lower() in valid_extensions:
                return str(file_path).replace("\\", "/")

    # 在 voices/emo_audios 中搜索 (为情感音频做同样的解析)
    emo_audios_dir = Path("voices/emo_audios")
    if emo_audios_dir.exists():
        # 第一遍：完全匹配文件名（即使用户可能传了扩展名）
        for file_path in emo_audios_dir.rglob("*"):
            if file_path.is_file() and file_path.name == name_or_path:
                return str(file_path).replace("\\", "/")
                
        # 第二遍：匹配 stem (不含扩展名)
        valid_extensions = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}
        for file_path in emo_audios_dir.rglob("*"):
            if file_path.is_file() and file_path.stem == name_or_path and file_path.suffix.lower() in valid_extensions:
                return str(file_path).replace("\\", "/")

    return name_or_path
