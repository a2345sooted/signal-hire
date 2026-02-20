import logging
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.db_models import User, UserTerms

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

    async def get_user_by_id_with_terms(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Returns a user by ID with terms_accepted preloaded.
        """
        from sqlalchemy.orm import selectinload
        stmt = select(User).options(selectinload(User.terms_accepted)).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_sub(self, sub: str) -> Optional[User]:
        """
        Returns a user by Auth0 sub.
        """
        stmt = select(User).where(User.sub == sub)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def accept_terms(self, user_id: uuid.UUID, version: str) -> UserTerms:
        """
        Records terms acceptance for a user.
        """
        user_terms = UserTerms(user_id=user_id, version=version)
        self.session.add(user_terms)
        await self.session.flush()
        return user_terms
