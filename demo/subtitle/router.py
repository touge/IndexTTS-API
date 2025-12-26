"""
@module: subtitle.router
@description: 该模块提供了字幕生成的API端点。

核心功能:
- 接收字幕生成请求，并将其作为一个后台任务进行处理。
- 利用 `ResourceManager` 实现任务排队，确保同一时间只有一个字幕生成任务在运行，避免资源冲突。
- 提供了任务状态查询的前置接口，客户端可以轮询任务状态。

设计模式:
- **异步任务处理**: 使用 FastAPI 的 `BackgroundTasks` 将耗时的字幕生成操作移至后台，实现API的快速响应。
- **资源锁与任务队列**: 通过 `ResourceManager` 单例来管理一个名为 "subtitle_generation" 的资源。
  - 当资源被锁定时，新的任务请求将被放入队列，并返回 `QUEUED` 状态及队列位置。
  - 当资源空闲时，任务将直接开始执行，并返回 `PENDING` 状态。
- **状态驱动**: 任务的整个生命周期（QUEUED -> PENDING -> RUNNING -> SUCCESS/FAILED）由 `TaskManager` 进行精确管理。
"""
import os
import sys
import base64
from fastapi import APIRouter, HTTPException, Depends, Body, Request, BackgroundTasks
from typing import Optional, Dict, Any
from pydantic import BaseModel
import httpx
from starlette.concurrency import run_in_threadpool  # 用于线程池执行阻塞操作

from src.engine.resource_manager import resource_manager
from src.engine.task_manager import TaskManager
from src.engine.security import verify_token
from src.logger import log
from src.utils import get_relative_url

from src.modules.subtitle.generator import Generator as SubtitleGenerator
from src.modules.subtitle.utils import validate_subtitle_generation_prerequisites

# 添加项目根路径，保证模块能正确导入
# project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)


# 定义此模块中所有任务共享的资源名称。
# ResourceManager 将使用此名称来确保一次只有一个字幕生成任务在运行。
STEP_NAME = "subtitle_generation"

# 路由定义：任务模块，自动带 Token 鉴权
router = APIRouter(
    prefix="/tasks",
    tags=["音频和字幕 - Audio and Subtitles"],
    dependencies=[Depends(verify_token)]
)

class SubtitleRequest(BaseModel):
    """
    定义字幕生成请求的JSON结构体。
    该模型用于数据校验和类型提示，但在此版本中，API端点未使用它作为请求体，
    因为所需信息已通过 task_id 间接获取。
    """
    audio_url: Optional[str] = ""
    audio_base64: Optional[str] = ""
    audio_file_bytes: Optional[bytes] = b""

async def _generate_subtitles_task(task_manager: TaskManager, request: Request):
    """
    后台执行的字幕生成任务。

    这是一个独立的异步函数，由 FastAPI 的 `BackgroundTasks` 在后台线程中调用。
    它遵循“获取锁 -> 执行任务 -> 释放锁”的模式，确保了资源的安全访问。

    Args:
        task_id (str): 当前任务的唯一标识符。
        request (Request): FastAPI 的请求对象，用于生成文件的可访问 URL。
    """
    # task_manager = TaskManager(task_id)

    try:
        # 关键点 1: 等待并获取资源锁
        # 这是任务队列的核心。如果资源正被占用，此任务会在此处异步等待，直到轮到它。
        # `wait_for_resource` 内部处理了从队列中取任务并设置事件的逻辑。
        await resource_manager.wait_for_resource(STEP_NAME, task_manager.task_id)

        # 关键点 2: 获取锁后，立刻更新状态为 RUNNING
        # 这向客户端表明，任务已不再排队或等待，而是真正在执行中。
        task_manager.update_status(
            TaskManager.STATUS_RUNNING,
            step=STEP_NAME,
            details={
                "message": "Subtitle generation task has started.",
                "queue_position": 0
            }
        )

        # 执行核心业务逻辑
        # 调用实际的字幕生成器。由于 `preprocessor.run` 是一个阻塞的I/O密集型操作，
        # 我们使用 `run_in_threadpool` 将其放入独立的线程中执行，避免阻塞事件循环。
        script_path = task_manager.get_file_path('original_doc')
        preprocessor = SubtitleGenerator(task_id=task_manager.task_id, doc_file=script_path)

        srt_path = await run_in_threadpool(preprocessor.run)
        srt_url = get_relative_url(srt_path, request)

        # 任务成功，准备最终结果
        details = {
            "message": "Subtitle generation completed successfully.",
            "generate_data": {
                "subtitle": {
                    "url": srt_url,
                    "final_srt_path": srt_path
                }
            }
        }
        task_manager.update_status(
            TaskManager.STATUS_SUCCESS,
            step=STEP_NAME,
            details=details
        )
        log.success(f"字幕生成任务 '{task_manager.task_id}' 成功完成。")

    except Exception as e:
        # 异常处理：记录错误并更新任务状态为 FAILED
        error_message = f"Subtitle generation failed: {str(e)}"
        log.error(f"Background subtitle generation task '{task_manager.task_id}' failed: {error_message}", exc_info=True)
        task_manager.update_status(
            TaskManager.STATUS_FAILED,
            step=STEP_NAME,
            details={"message": error_message}
        )
    finally:
        # 关键点 4: 确保资源锁在任务结束时被释放
        # `finally` 块保证了无论任务成功还是失败，资源锁都会被释放，
        # 从而允许队列中的下一个任务开始执行。这是保证系统健壮性的关键。
        resource_manager.release_resource(STEP_NAME)


@router.post("/{task_id}/subtitles", summary="为任务生成字幕")
async def generate_subtitles(
    task_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    # payload: SubtitleRequest = Body(...) # 当前版本未使用请求体
):
    """
    接收并处理字幕生成请求的API端点。

    此端点实现了非阻塞的请求处理模式：
    1.  快速进行前置条件验证。
    2.  检查资源锁状态，决定任务是立即开始还是进入队列。
    3.  将实际的耗时操作 (`_generate_subtitles_task`) 添加到后台任务中。
    4.  立即向客户端返回任务的初始状态（QUEUED 或 PENDING），实现快速响应。

    Args:
        task_id (str): 任务的唯一标识符，从 URL 路径中获取。
        background_tasks (BackgroundTasks): FastAPI 依赖注入，用于添加后台任务。
        request (Request): FastAPI 的请求对象。

    Returns:
        dict: 包含任务 ID、初始状态和消息的响应体。
    """
    task_manager = TaskManager(task_id)
    try:
        # --- 前置验证 ---
        validate_subtitle_generation_prerequisites(task_manager)

        # 无论任务是排队还是立即开始，都将其添加到后台任务中。
        # FastAPI 会在发送响应后开始执行此任务。
        background_tasks.add_task(_generate_subtitles_task, task_manager, request)

        # 在提交任务后，立即检查资源是否已被占用，以决定初始状态。
        is_busy = resource_manager.is_resource_locked(STEP_NAME)

        # 无论资源是否繁忙，都先将任务加入队列的“等候区”
        if resource_manager.get_queue_position(STEP_NAME, task_id) == 0:
            resource_manager._queues[STEP_NAME].append(task_id)

        # 如果资源繁忙，说明当前任务需要真正排队。
        if is_busy:
            queue_position = resource_manager.get_queue_position(STEP_NAME, task_id)
            status = TaskManager.STATUS_QUEUED
            message = f"Subtitle generation task is busy. Task has been queued at position {queue_position}."
            details = {"message": message, "queue_position": queue_position}
        # 如果资源空闲，说明当前任务会立刻开始。
        else:
            queue_position = 0 # 逻辑上不在队列中
            status = TaskManager.STATUS_PENDING # 初始状态为PENDING，后台会立刻更新为RUNNING
            message = "Subtitle generation task submitted. Processing will start immediately."
            details = {"message": message, "queue_position": queue_position}

        task_manager.update_status(
            status,
            step=STEP_NAME,
            details=details
        )

        # 立即返回响应给客户端
        return {
            "task_id": task_id,
            "status": status,
            "message": message,
            "queue_position": queue_position
        }

    except Exception as e:
        # 全局异常捕获，防止服务因意外错误而崩溃
        log.error(f"任务 '{task_id}' 提交失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {e}")
