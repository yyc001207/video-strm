from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OpenListTask(Base):
    """OpenList 任务配置表"""

    __tablename__ = "open_list_task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="任务名称")
    output_dir: Mapped[str] = mapped_column(String(512), nullable=False, comment="输出目录")
    process_path: Mapped[str] = mapped_column(String(512), nullable=False, comment="处理路径")
    pause_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="间隔文件数量（NULL=用全局配置）")
    pause_time: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="暂停时间（秒，逗号分隔；NULL=用全局配置）")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    executions: Mapped[list["OpenListExecution"]] = relationship(back_populates="task")

    __table_args__ = (
        {"comment": "OpenList 任务配置表"},
    )
