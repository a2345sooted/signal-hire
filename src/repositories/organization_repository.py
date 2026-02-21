import logging
import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.db_models import Organization, OrganizationUser, OrgRole

logger = logging.getLogger(__name__)

class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_organization(self, name: str, user_id: uuid.UUID) -> Organization:
        """
        Creates a new organization and assigns the user as OWNER.
        """
        # Simple slug generation: lower case and replace spaces with hyphens
        # In a real app, we'd want to handle non-alphanumeric chars and collisions
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        
        # Check for slug collision and append a random suffix if needed
        # For simplicity in this exploration project, we'll just check once
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none():
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        # Create organization
        org = Organization(name=name, slug=slug)
        self.session.add(org)
        await self.session.flush()

        # Assign user as OWNER
        org_user = OrganizationUser(
            org_id=org.id,
            user_id=user_id,
            role=OrgRole.OWNER
        )
        self.session.add(org_user)
        await self.session.flush()

        logger.info(f"Created organization '{name}' ({org.id}) for user {user_id} as OWNER")
        return org

    async def get_user_organizations(self, user_id: uuid.UUID) -> List[Organization]:
        """
        Returns all organizations the user belongs to.
        """
        stmt = (
            select(Organization)
            .join(OrganizationUser)
            .where(OrganizationUser.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_organization(self, org_id: uuid.UUID) -> Optional[Organization]:
        """
        Returns an organization by ID.
        """
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_organization_by_slug(self, slug: str) -> Optional[Organization]:
        """
        Returns an organization by slug.
        """
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_role_in_org(self, user_id: uuid.UUID, org_id: uuid.UUID) -> Optional[OrgRole]:
        """
        Returns the user's role in the specified organization.
        """
        stmt = select(OrganizationUser.role).where(
            OrganizationUser.user_id == user_id,
            OrganizationUser.org_id == org_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
