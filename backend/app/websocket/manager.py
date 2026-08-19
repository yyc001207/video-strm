"""WebSocket 连接管理：按 execution_id 分组广播实时日志。

设计参考《设计规范文档》§4.11：``ConnectionManager`` 维护
``execution_id -> [WebSocket]``，``broadcast`` 对单条连接发送失败时静默摘除，
避免单个断连客户端阻塞日志推送。
"""

from typing import Dict, List

from fastapi import WebSocket

from app.core.logger import logger


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, execution_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(execution_id, []).append(websocket)

    def disconnect(self, execution_id: int, websocket: WebSocket) -> None:
        conns = self.active_connections.get(execution_id)
        if conns and websocket in conns:
            conns.remove(websocket)
            if not conns:
                self.active_connections.pop(execution_id, None)

    async def broadcast(self, execution_id: int, message: dict) -> None:
        conns = self.active_connections.get(execution_id)
        for conn in list(conns or []):
            try:
                await conn.send_json(message)
            except Exception:
                self.disconnect(execution_id, conn)

    async def send_recent(self, execution_id: int, websocket: WebSocket, messages: list) -> None:
        for message in messages:
            try:
                await websocket.send_json(message)
            except Exception:
                break

    def has_connections(self, execution_id: int) -> bool:
        return bool(self.active_connections.get(execution_id))


ws_manager = ConnectionManager()
