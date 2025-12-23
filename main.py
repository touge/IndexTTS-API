import uvicorn
import bootstrap
import signal
import os
import logging
from app.utils.yaml_config_loader import YamlConfigLoader

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    主函数，封装了整个应用的启动逻辑。
    """
    # 1. 加载配置
    try:
        config = YamlConfigLoader("config.yaml")
        server_config = config.get('server', {})
        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 8000)
        reload = server_config.get('reload', False)
    except Exception as e:
        logger.warning(f"Failed to load config, using defaults: {e}")
        host = "0.0.0.0"
        port = 8000
        reload = False

    # 2. 打印启动信息
    print("\n" + "="*60)
    print("IndexTTS API - Service Starting...")
    print("="*60)
    print(f"Service Address: http://{host}:{port}")
    print(f"API Docs: http://127.0.0.1:{port}/docs")
    print("="*60)
    
    # 3. 设置信号处理器
    shutdown_count = 0
    def graceful_shutdown_handler(signum, frame):
        nonlocal shutdown_count
        shutdown_count += 1
        if shutdown_count == 1:
            print("\nShutdown signal received... Closing service.")
        else:
            print("\nForced exit!")
            os._exit(1)
            
    signal.signal(signal.SIGINT, graceful_shutdown_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, graceful_shutdown_handler)

    # 4. 启动服务器
    print(f"\nStarting FastAPI server...")
    print("Tip: Press Ctrl+C to stop the service.\n")
    
    try:
        uvicorn.run(
            "app.api.main:app",
            host=host,
            port=port,
            log_level="info",
            reload=reload
        )
    except SystemExit:
        pass
        
    print("\nService successfully stopped. Goodbye!")

if __name__ == "__main__":
    main()
