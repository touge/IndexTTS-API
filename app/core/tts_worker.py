"""
TTS生成工作线程
负责在后台执行TTS音频生成任务，并实时以信号形式报告进度。
"""
import logging
from PyQt6.QtCore import QThread, pyqtSignal
from typing import Dict, Any

logger = logging.getLogger(__name__)

class TTSWorker(QThread):
    """
    TTS生成工作线程
    
    Signals:
        progress_signal (int, str): 进度信号 (百分比(0-100), 状态描述)
        finished_signal (bool, str): 完成信号 (是否成功, 输出路径/错误信息)
    """
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, tts_generator, params: Dict[str, Any]):
        """
        初始化工作线程
        
        Args:
            tts_generator: TTSGenerator实例
            params: 生成参数字典
        """
        super().__init__()
        self.tts = tts_generator
        self.params = params
        self._is_running = True
        
    def run(self):
        """执行生成任务"""
        try:
            logger.info("TTSWorker开始执行任务...")
            self.progress_signal.emit(0, "准备开始生成...")
            
            # 使用回调函数适配 progress_signal
            def progress_callback(progress: int, status: str):
                if self._is_running:
                    self.progress_signal.emit(progress, status)
            
            # 注入回调
            self.params['progress_callback'] = progress_callback
            
            success = self.tts.generate(**self.params)
            
            if success:
                self.progress_signal.emit(100, "生成完成!")
                self.finished_signal.emit(True, self.params['output_path'])
            else:
                self.finished_signal.emit(False, "生成失败，请检查日志")
                
        except Exception as e:
            logger.error(f"TTSWorker执行异常: {e}", exc_info=True)
            self.finished_signal.emit(False, str(e))
            
    def stop(self):
        """停止任务(尽力而为)"""
        self._is_running = False
        # 注意: 简单的标志位无法强制中断正在进行的各种阻塞操作(如模型推理)
        # 但可以在回调中检查此标志来提前退出
