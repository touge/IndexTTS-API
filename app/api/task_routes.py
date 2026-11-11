import logging
from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Optional
from app.api.schemas import BaseResponse, TaskStatusResponse, FreeRequest, ModelConfigRequest
from app.core.queue_manager import QueueManager
from app.core.security import verify_token

logger = logging.getLogger(__name__)
router = APIRouter()

# 依赖注入占位符
def get_queue_manager():
    raise NotImplementedError

@router.get("/status/{task_id}", response_model=TaskStatusResponse, tags=["Common"])
async def get_task_status(
    task_id: str,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token) 
):
    """
    查询任务状态
    
    通过任务ID查询生成任务的当前状态和详细信息。
    """
    status = qm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**status)


@router.post("/cancel/{task_id}", response_model=BaseResponse, tags=["Common"])
async def cancel_task(
    task_id: str,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    """
    取消排队中或正在执行的任务。
    若任务正在 GPU 子进程中执行，将立即终止该推理子进程并释放显存。
    """
    ok, reason = await qm.cancel_task(task_id)
    if not ok:
        logger.warning(f"[API] Cancel requested for unknown task_id={task_id}")
        raise HTTPException(status_code=404, detail="Task not found")
    logger.info(f"[API] Task cancelled: task_id={task_id}, reason={reason}")
    return BaseResponse(code=0, message=f"Task cancellation handled ({reason})", data={"task_id": task_id, "reason": reason})


@router.post("/free", response_model=BaseResponse, tags=["System"])
async def free_vram(
    req: Optional[FreeRequest] = Body(default=None),
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    """
    释放显存接口（供 KamlPro free_api 调度切换时调用）。
    销毁空闲的 GPU Worker 子进程以 100% 回收显存与 CUDA Context，Web 主进程保持常驻在线。
    """
    logger.info(f"[API] /free invoked (payload={req.model_dump() if req else {}})")
    result = await qm.free_resources()
    logger.info(f"[API] /free completed: {result}")
    return BaseResponse(code=0, message=result.get("message", "ok"), data=result)


@router.get("/model/status", response_model=BaseResponse, tags=["System"])
async def get_model_status(
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    """查询当前模型配置与 GPU Worker 子进程状态"""
    return BaseResponse(code=0, message="查询成功", data=qm.get_model_status())


@router.post("/model/config", response_model=BaseResponse, tags=["System"])
async def update_model_config(
    req: ModelConfigRequest,
    qm: QueueManager = Depends(get_queue_manager),
    token: str = Depends(verify_token),
):
    """
    运行时更新模型启用策略，或显式触发按需加载 / 卸载。
    """
    try:
        logger.info(f"[API] /model/config requested: {req.model_dump(exclude_none=True)}")
        data = await qm.update_model_config(
            enabled_versions=req.enabled_versions,
            subtitle_enabled=req.subtitle_enabled,
            unload_after_gen=req.unload_after_gen,
            idle_unload_seconds=req.idle_unload_seconds,
            preload_version=req.preload_version,
            action=req.action,
            version=req.version,
            load_subtitle=req.load_subtitle,
        )
        logger.info(f"[API] /model/config applied: {data}")
        return BaseResponse(code=0, message="模型配置更新成功", data=data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_model_config", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail={"error": "worker_busy", "message": str(e)})
