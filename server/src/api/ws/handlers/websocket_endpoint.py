from fastapi import WebSocket, WebSocketDisconnect
import logging

from ....api.ws.manager import manager

logger = logging.getLogger(__name__)

async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await manager.send_personal_message("pong", websocket)
            else:
                await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Error in websocket_endpoint: {e}", exc_info=True)
        manager.disconnect(websocket)

async def optimize_websocket_endpoint(websocket: WebSocket, optimize_id: str):
    await manager.connect(websocket, optimize_id, connection_type="optimizer")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await manager.send_personal_message("pong", websocket)
            else:
                # For now, we just echo or acknowledge
                await manager.send_personal_message(f"Optimization {optimize_id} status requested", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, optimize_id, connection_type="optimizer")
    except Exception as e:
        logger.error(f"Error in optimize_websocket_endpoint: {e}", exc_info=True)
        manager.disconnect(websocket, optimize_id, connection_type="optimizer")

async def job_websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(websocket, job_id, connection_type="job")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await manager.send_personal_message("pong", websocket)
            else:
                # For now, we just echo or acknowledge
                await manager.send_personal_message(f"Job {job_id} status requested", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id, connection_type="job")
    except Exception as e:
        logger.error(f"Error in job_websocket_endpoint: {e}", exc_info=True)
        manager.disconnect(websocket, job_id, connection_type="job")
