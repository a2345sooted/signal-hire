import logging
from typing import List, Dict

from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.optimizer_connections: Dict[str, List[WebSocket]] = {}
        self.job_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, thread_id: str = None, connection_type: str = "optimizer"):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        if thread_id:
            if connection_type == "job":
                if thread_id not in self.job_connections:
                    self.job_connections[thread_id] = []
                self.job_connections[thread_id].append(websocket)
                logger.info(f"WebSocket connected for job_id: {thread_id}")
            else:
                if thread_id not in self.optimizer_connections:
                    self.optimizer_connections[thread_id] = []
                self.optimizer_connections[thread_id].append(websocket)
                logger.info(f"WebSocket connected for optimize_id: {thread_id}")
        else:
            logger.info("WebSocket connected")

    def disconnect(self, websocket: WebSocket, thread_id: str = None, connection_type: str = "optimizer"):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        if thread_id:
            target_dict = self.job_connections if connection_type == "job" else self.optimizer_connections
            if thread_id in target_dict:
                if websocket in target_dict[thread_id]:
                    target_dict[thread_id].remove(websocket)
                    if not target_dict[thread_id]:
                        del target_dict[thread_id]
            logger.info(f"WebSocket disconnected for {connection_type} thread_id: {thread_id}")
        else:
            logger.info("WebSocket disconnected")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_optimizer(self, message: str, optimize_id: str):
        if optimize_id in self.optimizer_connections:
            for connection in self.optimizer_connections[optimize_id]:
                await connection.send_text(message)

    async def broadcast_to_job(self, message: str, job_id: str):
        logger.info(f"Broadcasting to job {job_id}: {message}")
        if job_id in self.job_connections:
            logger.info(f"Found {len(self.job_connections[job_id])} connections for job {job_id}")
            for connection in self.job_connections[job_id]:
                try:
                    await connection.send_text(message)
                    logger.info(f"Successfully sent message to connection")
                except Exception as e:
                    logger.error(f"Failed to send message to connection: {e}")
        else:
            logger.warning(f"No active connections for job {job_id}. Active job_ids: {list(self.job_connections.keys())}")

manager = ConnectionManager()
