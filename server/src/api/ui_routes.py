from fastapi import APIRouter, Request, Depends
from fastapi.responses import FileResponse
import os
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db

router = APIRouter()

# Path to the Angular build directory
ui_dist_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "ui", "dist", "ui", "browser")

@router.get("/")
async def serve_ui_root():
    index_path = os.path.join(ui_dist_path, "index.html")
    if not os.path.exists(index_path):
        return {"error": "UI not built. Please run 'npm run build' in the ui directory."}
    return FileResponse(index_path)

@router.get("/{full_path:path}")
async def serve_angular(full_path: str):
    # If the request is for an API path, don't handle it here
    if full_path.startswith("api"):
        # We should NOT return None here, as it will be interpreted as a 200 OK with body 'null'
        # if this route matches. However, it's better to just skip this handler.
        # But in FastAPI, if a route matches, it handles it.
        # Since this is a catch-all, we should probably check if it's an API call and NOT handle it.
        # Actually, if we return None, FastAPI serializes it to null.
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    file_path = os.path.join(ui_dist_path, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # For index.html, we want to disable caching during development/transition
    # to avoid stale hydration errors if the user's browser cached an old version.
    return FileResponse(
        os.path.join(ui_dist_path, "index.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )

