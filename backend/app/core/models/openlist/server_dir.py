from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class OpenListServerDir(Base):
    """服务器父级目录配置表（一个服务器可配置多个父级目录）"""

    __tablename__ = "open_list_server_dir"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    server_id: Mapped[int] = mapped_column(ForeignKey("open_list_server.id"), nullable=False, comment="关联服务器 ID")
    path: Mapped[str] = mapped_column(String(512), nullable=False, comment="父级目录路径（以 / 开头）")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    __table_args__ = (
        Index("idx_server_dir", "server_id", "is_deleted"),
        {"comment": "服务器父级目录配置表"},
    )
