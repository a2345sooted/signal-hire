import logging
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.db_models import User

logger = logging.getLogger(__name__)

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Returns a user by ID.
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_sub(self, sub: str) -> Optional[User]:
        """
        Returns a user by Auth0 sub.
        """
        stmt = select(User).where(User.sub == sub)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

