import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.queue_manager import QueueManager
from app.api.v1_5 import routes as v1_5_routes
from app.api.v2_0 import routes as v2_0_routes
from app.api import task_routes
from app.api import download_routes
from app.api import subtitle_routes

from app.api import speaker, emo, static_routes

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

# 全局异常处理，统一返回格式
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    message = str(detail)
    code = exc.status_code
    
    # 尝试从业务侧手动抛出的字典型 detail 提取字段
    if isinstance(detail, dict):
        message = detail.get("error", message)
        code = detail.get("code", code)
        
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "failed",
            "code": code,
            "message": message,
            "data": None
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # 抽取只读第一条的简短抛出信息
    err = exc.errors()[0] if exc.errors() else {}
    msg = f"参数错误: {err.get('loc', [''])[0]} - {err.get('msg', 'validation error')}"
    return JSONResponse(
        status_code=422,
        content={
            "status": "failed",
            "code": -1,
            "message": msg,
            "data": None
        }
    )


# 依赖注入覆盖
def get_queue_manager_override():
    return queue_manager

app.dependency_overrides[v1_5_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[v2_0_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[task_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[download_routes.get_queue_manager] = get_queue_manager_override
app.dependency_overrides[subtitle_routes.get_queue_manager] = get_queue_manager_override

# 注册路由
app.include_router(task_routes.router) # 挂载在根路径，即 /status/{task_id}
app.include_router(speaker.router, prefix="/speaker", tags=["Speaker"]) # 发音人路由
app.include_router(emo.router, prefix="/emo", tags=["Emotion"]) # 情绪音路由
app.include_router(static_routes.router, prefix="/static", tags=["Static"]) # 静态资源路由
app.include_router(download_routes.router) # 下载路由，/download/{task_id} 和 /files/{task_id}
app.include_router(subtitle_routes.router, prefix="/subtitle", tags=["Subtitle"]) # 字幕生成路由
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
            "subtitle": "/subtitle/generate",
            "status": "/status/{task_id}",
            "speaker": "/speaker",
            "emo": "/emo",
            "static_voices": "/static/voices/{file_path}",
            "docs": "/docs"
        }
    }
