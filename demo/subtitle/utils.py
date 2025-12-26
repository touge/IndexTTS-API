import os
from src.engine.task_manager import TaskManager

def validate_subtitle_generation_prerequisites(task_manager: TaskManager):
    """
    验证字幕生成所需的前置条件。
    
    在开始字幕生成任务之前，此函数会检查必要的依赖文件（如原始文稿）是否存在且不为空。
    这是确保任务能够顺利执行的第一道防线。

    Args:
        task_manager (TaskManager): 与当前任务关联的任务管理器实例。

    Raises:
        FileNotFoundError: 如果所需的文稿文件不存在。
        ValueError: 如果文稿文件为空。
    """
    script_path = task_manager.get_file_path('original_doc')
    if not script_path or not os.path.exists(script_path):
        raise FileNotFoundError(f"Prerequisite script file ('original_doc') not found at path: {script_path}")

    # 检查脚本文件内容是否为空
    with open(script_path, 'r', encoding='utf-8') as f:
        if not f.read().strip():
            raise ValueError(f"Prerequisite script file is empty: {script_path}")