from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OpenListExecution(Base):
    """OpenList 执行记录表"""

    __tablename__ = "open_list_execution"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    task_id: Mapped[int] = mapped_column(ForeignKey("open_list_task.id"), nullable=False, comment="关联任务 ID")
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称（冗余，避免关联查询）")
    server_id: Mapped[Optional[int]] = mapped_column(ForeignKey("open_list_server.id"), nullable=True, comment="关联服务器 ID（可空，兼容旧记录）")
    server_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="服务器名称（冗余快照）")
    status: Mapped[str] = mapped_column(Enum("running", "success", "fail", "cancelled", name="open_list_execution_status"), nullable=False, default="running", comment="执行状态")
    video_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="视频处理成功数")
    video_total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="视频总数")
    subtitle_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="字幕处理成功数")
    subtitle_total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="字幕总数")
    is_incremental: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否增量更新")
    is_force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否强制重新生成")
    strm_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="仅更新 strm（不重新下载已存在的字幕）")
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="耗时（秒）")
    log_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="日志文件路径")
    started_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="开始执行时间")
    finished_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="执行结束时间")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    task: Mapped["OpenListTask"] = relationship(back_populates="executions")
    logs: Mapped[list["OpenListLog"]] = relationship(back_populates="execution")

    __table_args__ = (
        Index("idx_task_id", "task_id"),
        Index("idx_status", "status"),
        Index("idx_started", "started_time"),
        {"comment": "OpenList 执行记录表"},
    )
