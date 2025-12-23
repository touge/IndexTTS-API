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
    
    ## 任务状态说明
    
    - **pending**: 排队中，等待执行
    - **processing**: 正在执行中
    - **completed**: 已完成，可获取结果
    - **failed**: 执行失败，查看 error 字段了解原因
    
    ## 队列位置说明
    
    - **queue_position = 0**: 任务正在执行
    - **queue_position = 1**: 排队中，前面还有 1 个任务
    - **queue_position = 2**: 排队中，前面还有 2 个任务
    - **queue_position = None**: 任务已完成或失败
    
    ## 返回字段
    
    **顶层字段**（基础信息）:
    ```json
    {
        "task_id": "xxx-xxx-xxx",
        "status": "processing",
        "created_at": "2024-12-23 16:30:15"
    }
    ```
    
    **details 字段**（详细信息）:
    ```json
    {
        "details": {
            "result": null,
            "error": null,
            "queue_position": 0,
            "queue_size": 3,
            "created_timestamp": 1703318415.0
        }
    }
    ```
    
    - **task_id**: 任务唯一标识符
    - **status**: 任务状态 (pending/processing/completed/failed)
    - **created_at**: 任务创建时间（人类可读格式，如 "2024-12-23 16:30:15"）
    - **details.result**: 生成的音频文件路径 (仅 completed 状态)
    - **details.error**: 错误信息 (仅 failed 状态)
    - **details.queue_position**: 队列位置 (0=执行中, >=1=排队中, None=已结束)
    - **details.queue_size**: 当前队列总大小
    - **details.created_timestamp**: 原始Unix时间戳（用于程序处理）
    
    ## 使用示例
    
    **Python**:
    ```python
    import requests
    import time
    
    headers = {"Authorization": "Bearer your-token"}
    
    # 提交任务
    response = requests.post(
        "http://localhost:8000/v2.0/generate",
        headers=headers,
        json={"text": "测试", "spk_audio_prompt": "speaker.wav"}
    )
    task_id = response.json()["task_id"]
    
    # 轮询状态
    while True:
        status = requests.get(
            f"http://localhost:8000/status/{task_id}",
            headers=headers
        ).json()
        
        print(f"状态: {status['status']}, 队列位置: {status['details']['queue_position']}")
        
        if status["status"] == "completed":
            print(f"完成！文件: {status['details']['result']}")
            break
        elif status["status"] == "failed":
            print(f"失败：{status['details']['error']}")
            break
        
        time.sleep(2)
    ```
    
    **cURL**:
    ```bash
    curl -X GET "http://localhost:8000/status/xxx-xxx-xxx" \
      -H "Authorization: Bearer your-token"
    ```
    
    ## 认证
    需要 Bearer Token 认证（如果在 config.yaml 中配置了 token）
    """
    status = qm.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(**status)
