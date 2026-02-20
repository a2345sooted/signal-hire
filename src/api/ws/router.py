from fastapi import APIRouter, WebSocket

from src.api.ws.handlers.websocket_endpoint import (
    websocket_endpoint, 
    optimize_websocket_endpoint,
    job_websocket_endpoint
)

router = APIRouter()

@router.websocket("/ping")
async def websocket_route(websocket: WebSocket):
    await websocket_endpoint(websocket)

@router.websocket("/optimize/{optimize_id}")
async def optimize_websocket_route(websocket: WebSocket, optimize_id: str):
    await optimize_websocket_endpoint(websocket, optimize_id)

@router.websocket("/job/{job_id}")
async def job_websocket_route(websocket: WebSocket, job_id: str):
    await job_websocket_endpoint(websocket, job_id)
