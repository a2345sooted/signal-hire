import logging
from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

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
    user = await repo.get_user_by_id(user_id)
    
    if not user:
        logger.error(f"User with ID {user_id} not found in database.")
        raise HTTPException(status_code=404, detail="User not found")

    return user
