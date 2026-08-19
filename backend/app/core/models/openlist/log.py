from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base


class OpenListLog(Base):
    """OpenList 实时日志表"""

    __tablename__ = "open_list_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    execution_id: Mapped[int] = mapped_column(ForeignKey("open_list_execution.id"), nullable=False, comment="关联执行记录 ID")
    log_level: Mapped[str] = mapped_column(Enum("info", "warn", "error", "progress", name="open_list_log_level"), nullable=False, default="info", comment="日志级别")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="日志内容")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True, comment="附加数据（如进度百分比、文件名等）")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="日志时间")

    execution: Mapped["OpenListExecution"] = relationship(back_populates="logs")

    __table_args__ = (
        Index("idx_execution_id", "execution_id"),
        Index("idx_log_level", "log_level"),
        Index("idx_created", "created_time"),
        {"comment": "OpenList 实时日志表"},
    )
