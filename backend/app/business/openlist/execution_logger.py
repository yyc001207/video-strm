"""单次执行的日志通道：把生成器日志转发到 WebSocket + 批量落库 + 日志文件。

STRMGenerator/OpenListAPI 使用标准 logging；本模块提供一个 logging.Handler，
将每条记录放入 ``asyncio.Queue``，由 ``LogPump`` 协程消费：广播 WS 帧、攒批
写入 ``open_list_log``、追加到本次执行的日志文件。队列有界，满了丢弃最旧以
保证日志推送永不阻塞生成器。
"""

import logging
import time
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logger import logger
from app.core.models import OpenListLog
from app.websocket.manager import ws_manager

STOP = object()

_LEVEL_MAP = {"debug": "info", "info": "info", "warning": "warn", "warn": "warn", "error": "error", "critical": "error"}


def map_level(levelname: str) -> str:
    return _LEVEL_MAP.get(levelname.lower(), "info")


def format_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


class ExecutionLogHandler(logging.Handler):
    """同步 Handler：把日志记录写入 asyncio.Queue（有界，满了丢弃）。"""

    def __init__(self, queue, maxsize: int = 5000):
        super().__init__()
        self.queue = queue
        self.maxsize = maxsize
        self.dropped = 0

    def emit(self, record: logging.LogRecord):
        try:
            message = record.getMessage()
            item = (time.time(), map_level(record.levelname), message)
            try:
                self.queue.put_nowait(item)
            except Exception:
                self.dropped += 1
        except Exception:
            pass


class LogPump:
    """消费队列：广播 WS 帧、攒批落库（可选）、追加日志文件、推送进度。

    persist_to_db=False 时跳过 DB 落库，日志以文件为准（open_list_log 不再增长）。
    """

    def __init__(
        self,
        execution_id: int,
        session_factory: async_sessionmaker,
        queue,
        log_file_path: str,
        progress: Dict[str, int],
        persist_to_db: bool = True,
    ):
        self.execution_id = execution_id
        self.session_factory = session_factory
        self.queue = queue
        self.log_file_path = log_file_path
        self.progress = progress
        self.persist_to_db = persist_to_db
        self.batch: list[dict] = []
        self.batch_size = 200
        self.last_progress_frame: Optional[str] = None

    async def broadcast(self, message: dict):
        try:
            await ws_manager.broadcast(self.execution_id, message)
        except Exception:
            pass

    def _progress_frame(self) -> dict:
        return {
            "type": "progress",
            "data": {
                "totalVideos": self.progress.get("totalVideos", 0),
                "successVideos": self.progress.get("successVideos", 0),
                "totalSubtitles": self.progress.get("totalSubtitles", 0),
                "successSubtitles": self.progress.get("successSubtitles", 0),
            },
        }

    async def maybe_progress(self):
        frame = self._progress_frame()
        key = frame["data"]
        if key != self.last_progress_frame:
            self.last_progress_frame = key
            await self.broadcast(frame)

    def _log_line(self, item) -> str:
        ts, level, message = item
        return f"[{format_ts(ts)}] [{level.upper()}] {message}"

    async def _append_file(self, line: str):
        try:
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    async def flush_batch(self, db: AsyncSession):
        if not self.batch:
            return
        # persist_to_db=False：跳过 DB 落库，日志以文件为准
        if not self.persist_to_db:
            self.batch.clear()
            return
        try:
            db.add_all(
                OpenListLog(
                    execution_id=self.execution_id,
                    log_level=row["level"],
                    content=row["content"],
                    metadata_=row.get("metadata"),
                )
                for row in self.batch
            )
            await db.commit()
            self.batch.clear()
        except Exception as exc:
            logger.error(f"OpenList 日志落库失败 execution={self.execution_id}: {exc}")
            self.batch.clear()

    async def run(self):
        db = self.session_factory()
        try:
            while True:
                item = await self.queue.get()
                if item is STOP:
                    break
                ts, level, message = item
                await self.broadcast(
                    {"type": "log", "level": level, "message": message, "ts": format_ts(ts)}
                )
                if self.persist_to_db:
                    self.batch.append(
                        {"level": level, "content": message, "metadata": None}
                    )
                    if len(self.batch) >= self.batch_size:
                        await self.flush_batch(db)
                await self._append_file(self._log_line(item))
                await self.maybe_progress()
        finally:
            try:
                await self.flush_batch(db)
            except Exception:
                pass
            try:
                await db.close()
            except Exception:
                pass
        await self.broadcast(self._progress_frame())

    async def stop(self):
        await self.queue.put(STOP)

    async def write_status(self, status: str, **counts):
        """执行结束/取消/失败时推送最终状态帧。"""
        frame = {
            "type": "status",
            "status": status,
            "video_success_count": self.progress.get("successVideos", 0),
            "video_total_count": self.progress.get("totalVideos", 0),
            "subtitle_success_count": self.progress.get("successSubtitles", 0),
            "subtitle_total_count": self.progress.get("totalSubtitles", 0),
            **counts,
        }
        await self.broadcast(frame)
