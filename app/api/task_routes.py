import logging
from fastapi import APIRouter, HTTPException, Depends
from app.api.schemas import TaskStatusResponse
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
