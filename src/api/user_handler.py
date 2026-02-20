import logging
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import uuid
from datetime import datetime

from src.database import get_db
from src.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

class UserResponse(BaseModel):
    id: uuid.UUID
    sub: str
    email: str
    created_at: datetime
    terms_accepted: bool = False

    class Config:
        from_attributes = True

class AcceptTermsRequest(BaseModel):
    version: str

async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the current authenticated user's information.
    The user is already created/synced by AuthMiddleware.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        logger.error("User ID not found in request state. This should be set by AuthMiddleware.")
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = UserRepository(db)
    user = await repo.get_user_by_id_with_terms(user_id)
    
    if not user:
        logger.error(f"User with ID {user_id} not found in database.")
        raise HTTPException(status_code=404, detail="User not found")

    # Calculate boolean first
    is_accepted = len(user.terms_accepted) > 0
    
    # Create the response dictionary manually to avoid validation errors
    user_data = {
        "id": user.id,
        "sub": user.sub,
        "email": user.email,
        "created_at": user.created_at,
        "terms_accepted": is_accepted
    }
    
    return UserResponse.model_validate(user_data)

async def accept_terms(
    request: Request,
    body: AcceptTermsRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Records terms acceptance for the current user.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = UserRepository(db)
    await repo.accept_terms(user_id, body.version)
    await db.commit()

    return {"success": True, "message": f"Terms version {body.version} accepted"}
