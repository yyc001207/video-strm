"""OpenList 执行引擎：后台运行 STRM 生成任务，实时日志推送 + 落库 + 结果回写。

``start_execution`` 校验通过后创建执行记录并 ``asyncio.create_task`` 启动
``run_generation``；后者在独立数据库会话中运行（请求会话在端点返回后即关闭）。
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from app.business.openlist.execution_logger import ExecutionLogHandler, LogPump
from app.business.openlist.strm_generator import STRMGenerator
from app.business.openlist.task_status_manager import TaskStatusManager
from app.core.database import AsyncSessionLocal
from app.core.logger import logger
from app.core.models import OpenListExecution
from app.core.settings import settings

# 并发信号量：限制同时运行的执行任务个数（默认 1）。
# run_generation 进入时 acquire、退出时 release；获取的是快照引用，
# 避免 set_semaphore_size 替换 _sem 后新旧信号量计数相互干扰。
_sem: asyncio.Semaphore = asyncio.Semaphore(1)


def set_semaphore_size(size: int) -> None:
    """按全局配置 max_concurrent 调整并发上限（默认 1，最小 1）。"""
    global _sem
    _sem = asyncio.Semaphore(max(1, int(size)))


def _build_per_execution_logger(execution_id: int, queue) -> logging.Logger:
    exe_logger = logging.getLogger(f"strm.execution_{execution_id}")
    exe_logger.handlers.clear()
    exe_logger.setLevel(logging.INFO)
    exe_logger.propagate = False
    exe_logger.addHandler(ExecutionLogHandler(queue))
    return exe_logger


async def _finish_execution(
    execution_id: int,
    status: str,
    progress: Dict[str, int],
    duration_seconds: int,
    log_path: str,
):
    try:
        async with AsyncSessionLocal() as db:
            execution = await db.get(OpenListExecution, execution_id)
            if execution is None:
                return
            execution.status = status
            execution.video_success_count = progress.get("successVideos", 0)
            execution.video_total_count = progress.get("totalVideos", 0)
            execution.subtitle_success_count = progress.get("successSubtitles", 0)
            execution.subtitle_total_count = progress.get("totalSubtitles", 0)
            execution.duration_seconds = duration_seconds
            execution.finished_time = datetime.now()
            execution.log_path = log_path
            await db.commit()
    except Exception as exc:
        logger.error(f"OpenList 执行结果回写失败 execution={execution_id}: {exc}")


async def run_generation(
    *,
    execution_id: int,
    task_id: int,
    output_dir: str,
    process_path: str,
    is_force: bool,
    global_config: Dict[str, object],
    pause_count: Optional[int] = None,
    pause_time: Optional[str] = None,
    strm_only: bool = False,
):
    # 并发控制：进入前 acquire 当前信号量快照，退出时对同一对象 release，
    # 保证并发计数在整个任务生命周期内正确占用（含排队等待）。
    sem = _sem
    await sem.acquire()
    task_key = str(task_id)
    started = time.monotonic()
    try:
        log_dir = Path(settings.openlist_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = str(log_dir / f"execution_{execution_id}.log")
    except Exception:
        log_path = ""

    queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
    exe_logger = _build_per_execution_logger(execution_id, queue)
    progress: Dict[str, int] = {
        "totalVideos": 0,
        "successVideos": 0,
        "errorVideos": 0,
        "totalSubtitles": 0,
        "successSubtitles": 0,
        "errorSubtitles": 0,
    }

    # 限流参数：任务级优先，为 NULL/空则回退全局配置（global_config 提供 pauseCount/pauseTime）
    task_config = {
        "outputDir": output_dir,
        "processPath": process_path,
        "pauseCount": pause_count if pause_count is not None else global_config.get("pauseCount"),
        "pauseTime": pause_time if pause_time else global_config.get("pauseTime"),
    }
    generator = STRMGenerator(global_config, task_config, task_id=task_key, logger_=exe_logger)
    persist_to_db = bool(global_config.get("logToDb", False))
    pump = LogPump(execution_id, AsyncSessionLocal, queue, log_path, generator.stats, persist_to_db=persist_to_db)
    pump_task = asyncio.create_task(pump.run())

    status = "success"
    try:
        await generator.execute(force=is_force, strm_only=strm_only, cleanup=True)
        if TaskStatusManager.is_cancelled(task_key):
            status = "cancelled"
            exe_logger.warning("任务已被取消")
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except Exception as exc:
        status = "fail"
        exe_logger.error(f"任务执行失败: {exc}")
        logger.exception(f"OpenList 执行异常 execution={execution_id}")

    duration = int(time.monotonic() - started)

    try:
        await asyncio.wait_for(pump.stop(), timeout=5)
    except Exception:
        pass
    try:
        await asyncio.wait_for(pump_task, timeout=10)
    except Exception:
        pump_task.cancel()

    await _finish_execution(execution_id, status, generator.stats, duration, log_path)
    try:
        await pump.write_status(status)
    except Exception:
        pass
    try:
        exe_logger.handlers.clear()
    except Exception:
        pass
    sem.release()
