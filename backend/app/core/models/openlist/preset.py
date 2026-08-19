from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class OpenListPreset(Base):
    """OpenList 预设配置表"""

    __tablename__ = "open_list_preset"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="预设名称")
    preset_path: Mapped[str] = mapped_column(String(512), nullable=False, comment="预设路径（自动填充至任务的处理路径和输出目录）")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序值")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    __table_args__ = (
        Index("idx_sort", "sort_order"),
        {"comment": "OpenList 预设配置表"},
    )
