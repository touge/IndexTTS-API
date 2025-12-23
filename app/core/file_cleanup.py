"""
定时清理过期文件的后台任务
"""

import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from app.utils.yaml_config_loader import yaml_config_loader

logger = logging.getLogger(__name__)

class FileCleanupService:
    """文件清理服务"""
    
    def __init__(self):
        self.running = False
    
    def start(self):
        """启动清理服务（在后台线程中运行）"""
        import threading
        self.running = True
        thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        thread.start()
        logger.info("File cleanup service started")
    
    def stop(self):
        """停止清理服务"""
        self.running = False
        logger.info("File cleanup service stopped")
    
    def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                self.cleanup_old_files()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)
            
            # 每小时执行一次清理
            time.sleep(3600)
    
    def cleanup_old_files(self):
        """清理过期文件"""
        tasks_dir = yaml_config_loader.get('api.output.tasks_dir', 'output/tasks')
        retention_hours = yaml_config_loader.get('api.output.retention_hours', 24)
        
        if not os.path.exists(tasks_dir):
            return
        
        cutoff_time = datetime.now() - timedelta(hours=retention_hours)
        deleted_count = 0
        
        # 遍历所有任务目录
        for task_dir_name in os.listdir(tasks_dir):
            task_dir_path = os.path.join(tasks_dir, task_dir_name)
            
            if not os.path.isdir(task_dir_path):
                continue
            
            try:
                # 获取目录创建时间
                dir_ctime = datetime.fromtimestamp(os.path.getctime(task_dir_path))
                
                # 如果超过保留时间，删除整个目录
                if dir_ctime < cutoff_time:
                    self._remove_directory(task_dir_path)
                    deleted_count += 1
                    logger.info(f"Deleted expired task directory: {task_dir_path}")
            
            except Exception as e:
                logger.warning(f"Failed to process directory {task_dir_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleanup completed: {deleted_count} task directories deleted")
    
    def _remove_directory(self, dir_path: str):
        """递归删除目录及其内容"""
        import shutil
        shutil.rmtree(dir_path, ignore_errors=True)


# 全局清理服务实例
cleanup_service = FileCleanupService()
