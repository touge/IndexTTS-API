import uvicorn
import bootstrap
import signal
import os
import logging
import argparse
from app.utils.yaml_config_loader import YamlConfigLoader

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """
    主函数，封装了整个应用的启动逻辑。
    Command-line arguments take priority over config.yaml values.
    """
    # 1. 加载配置（作为默认值）
    try:
        config = YamlConfigLoader("config.yaml")
        server_config = config.get('server', {})
        cfg_host = server_config.get('host', '0.0.0.0')
        cfg_port = server_config.get('port', 8000)
        cfg_reload = server_config.get('reload', False)
    except Exception as e:
        logger.warning(f"Failed to load config, using defaults: {e}")
        cfg_host = "0.0.0.0"
        cfg_port = 8000
        cfg_reload = False

    # 2. 解析命令行参数（覆盖 config.yaml 中的值）
    parser = argparse.ArgumentParser(description="IndexTTS API Server")
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,
        help=f"Server port (default from config.yaml: {cfg_port})"
    )
    parser.add_argument(
        "-ip", "--host",
        type=str,
        default=None,
        help=f"Server host (default from config.yaml: {cfg_host})"
    )
    parser.add_argument(
        "-r", "--reload",
        action="store_true",
        default=None,
        help="Enable auto-reload (default from config.yaml)"
    )
    args = parser.parse_args()

    # 命令行参数优先，未传入则使用 config.yaml 的值
    host   = args.host   if args.host   is not None else cfg_host
    port   = args.port   if args.port   is not None else cfg_port
    reload = args.reload if args.reload is not None else cfg_reload

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
