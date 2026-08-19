from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class OpenListServer(Base):
    """OpenList 服务器配置表（支持多服务器，每行一条）"""

    __tablename__ = "open_list_server"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, comment="主键")
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="服务器名称")
    server_url: Mapped[str] = mapped_column(String(512), nullable=False, comment="服务器地址（AList/OpenList API 地址）")
    token: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="认证令牌（加密存储）")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    created_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="逻辑删除")

    __table_args__ = (
        {"comment": "OpenList 服务器配置表"},
    )
