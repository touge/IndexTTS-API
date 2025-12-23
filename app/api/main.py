import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from app.core.queue_manager import QueueManager
from app.api.v1_5 import routes as v1_5_routes
from app.api.v2_0 import routes as v2_0_routes
from app.api import common_routes
from app.api import download_routes
from app.api import upload_routes
from app.core.security import verify_token

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 全局 QueueManager
queue_manager = QueueManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    from app.core.file_cleanup import cleanup_service
    await queue_manager.start()
    cleanup_service.start()  # 启动文件清理服务
    yield
    # 关闭时
    cleanup_service.stop()  # 停止文件清理服务
    await queue_manager.stop()

app = FastAPI(
    title="IndexTTS API",
    description="支持 V1.5 和 V2.0 的 TTS 生成 API",
    version="1.0.0",
    lifespan=lifespan
)

# 依赖注入覆盖
def get_queue_manager_override():
    return queue_manager

app.dependency_overrides[v1_5_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[v2_0_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[common_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[download_routes.get_queue_manager] = get_queue_manager_override

# 注册路由
app.include_router(common_routes.router) # 挂载在根路径，即 /status/{task_id}
app.include_router(download_routes.router) # 下载路由，/download/{task_id} 和 /files/{task_id}
app.include_router(upload_routes.router) # 上传路由，/upload/audio
app.include_router(v1_5_routes.router, prefix="/v1.5", tags=["V1.5"])
app.include_router(v2_0_routes.router, prefix="/v2.0", tags=["V2.0"])

@app.get("/")
async def root(token: str = Depends(verify_token)):
    """
    API 根路径
    
    返回 API 运行状态信息。
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）。
    """
    return {
        "message": "IndexTTS API is running. Check /docs for documentation.",
        "version": "1.0.0",
        "endpoints": {
            "v1.5": "/v1.5/generate",
            "v2.0": ["/v2.0/generate", "/v2.0/emo_mode/generate"],
            "status": "/status/{task_id}",
            "docs": "/docs"
        }
    }

