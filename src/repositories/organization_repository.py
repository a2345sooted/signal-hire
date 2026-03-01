import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.db_models import Organization, OrganizationUser, OrgRole, User, OrganizationInvite

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

    async def get_organization_members(self, org_id: uuid.UUID) -> List[dict]:
        """
        Returns all members (active and pending) of an organization.
        """
        # Fetch active members and join with their respective invitations if available
        # to see if they joined with a different email.
        stmt_members = (
            select(
                OrganizationUser.id,
                OrganizationUser.user_id,
                User.email,
                OrganizationUser.role,
                OrganizationUser.created_at,
                OrganizationInvite.email.label("invited_email")
            )
            .join(User, OrganizationUser.user_id == User.id)
            .outerjoin(
                OrganizationInvite,
                (OrganizationInvite.org_id == OrganizationUser.org_id) & 
                (OrganizationInvite.accepted_email == User.email)
            )
            .where(OrganizationUser.org_id == org_id)
        )
        result_members = await self.session.execute(stmt_members)
        members = []
        for row in result_members.all():
            row_dict = row._asdict()
            d = {
                "id": row_dict["id"],
                "user_id": row_dict["user_id"],
                "email": row_dict["email"],
                "role": row_dict["role"],
                "created_at": row_dict["created_at"],
                "status": "ACTIVE",
                "accepted_email": None
            }
            
            # If they joined via an invite that had a different email, capture it.
            if row_dict["invited_email"] and row_dict["invited_email"].lower() != row_dict["email"].lower():
                d["accepted_email"] = row_dict["email"]
                # We show the original invited email as the primary 'email' in the list
                # so the admin recognizes who they invited.
                d["email"] = row_dict["invited_email"]

            members.append(d)

        # Fetch pending invites
        # Exclude those that are for emails already in the organization as active members
        active_emails = {m["email"].lower() for m in members}
        stmt_invites = (
            select(
                OrganizationInvite.id,
                OrganizationInvite.email,
                OrganizationInvite.role,
                OrganizationInvite.created_at
            )
            .where(
                OrganizationInvite.org_id == org_id,
                OrganizationInvite.accepted_at == None,
                OrganizationInvite.expires_at > datetime.now(timezone.utc)
            )
        )
        result_invites = await self.session.execute(stmt_invites)
        invites = []
        for row in result_invites.all():
            d = row._asdict()
            if d["email"].lower() in active_emails:
                continue
            d["status"] = "PENDING"
            d["user_id"] = None
            invites.append(d)

        return members + invites

    async def create_organization_invite(
        self, 
        org_id: uuid.UUID, 
        email: str, 
        role: OrgRole, 
        inviter_id: uuid.UUID,
        expiry_days: int = 7
    ) -> OrganizationInvite:
        """
        Creates a new organization invitation.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(days=expiry_days)
        
        invite = OrganizationInvite(
            org_id=org_id,
            email=email.lower(),
            role=role,
            inviter_id=inviter_id,
            expires_at=expires_at
        )
        self.session.add(invite)
        await self.session.flush()
        
        logger.info(f"Created invitation for {email} to join {org_id} as {role}")
        return invite

    async def resend_organization_invite(
        self,
        org_id: uuid.UUID,
        invite_id: uuid.UUID,
        expiry_days: int = 7
    ) -> Optional[OrganizationInvite]:
        """
        Resets the expiration date of an invitation.
        """
        stmt = select(OrganizationInvite).where(
            OrganizationInvite.id == invite_id,
            OrganizationInvite.org_id == org_id
        )
        result = await self.session.execute(stmt)
        invite = result.scalar_one_or_none()
        
        if not invite:
            return None

        invite.expires_at = datetime.now(timezone.utc) + timedelta(days=expiry_days)
        await self.session.flush()
        
        logger.info(f"Resent invitation {invite_id} for org {org_id}")
        return invite

    async def delete_organization_invite(
        self,
        org_id: uuid.UUID,
        invite_id: uuid.UUID
    ) -> bool:
        """
        Deletes (cancels) an invitation.
        """
        from sqlalchemy import delete
        stmt = delete(OrganizationInvite).where(
            OrganizationInvite.id == invite_id,
            OrganizationInvite.org_id == org_id
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} invitation(s) with ID {invite_id} for org {org_id}")
        return deleted_count > 0

    async def remove_organization_member(self, org_id: uuid.UUID, member_id: uuid.UUID) -> bool:
        """
        Removes a member from an organization.
        member_id is the record ID in organization_users table.
        """
        from sqlalchemy import delete
        stmt = delete(OrganizationUser).where(
            OrganizationUser.id == member_id,
            OrganizationUser.org_id == org_id
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        
        deleted_count = result.rowcount
        logger.info(f"Removed {deleted_count} member(s) with record ID {member_id} from org {org_id}")
        return deleted_count > 0

    async def get_invite(self, invite_id: uuid.UUID) -> Optional[OrganizationInvite]:
        """
        Returns an invitation by ID.
        """
        stmt = select(OrganizationInvite).where(OrganizationInvite.id == invite_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def accept_invite(self, invite_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Accepts an invitation.
        Links the user to the organization and marks the invite as accepted.
        """
        # 0. Get user email
        stmt_user = select(User.email).where(User.id == user_id)
        result_user = await self.session.execute(stmt_user)
        user_email = result_user.scalar_one_or_none()

        # 1. Get the invite
        stmt = select(OrganizationInvite).where(OrganizationInvite.id == invite_id)
        result = await self.session.execute(stmt)
        invite = result.scalar_one_or_none()
        
        if not invite:
            logger.warning(f"Attempted to accept non-existent invite {invite_id}")
            return False
            
        if invite.accepted_at:
            logger.warning(f"Attempted to accept already accepted invite {invite_id}")
            return False
            
        if invite.expires_at < datetime.now(timezone.utc):
            logger.warning(f"Attempted to accept expired invite {invite_id}")
            return False

        # 2. Check if user is already a member
        stmt_member = select(OrganizationUser).where(
            OrganizationUser.org_id == invite.org_id,
            OrganizationUser.user_id == user_id
        )
        result_member = await self.session.execute(stmt_member)
        if result_member.scalar_one_or_none():
            logger.info(f"User {user_id} is already a member of org {invite.org_id}")
            # Mark invite as accepted anyway if they are already in? 
            # Or just fail? Let's just mark it accepted and move on.
            invite.accepted_at = datetime.now(timezone.utc)
            invite.accepted_email = user_email

            from sqlalchemy import update
            stmt_others = (
                update(OrganizationInvite)
                .where(
                    OrganizationInvite.org_id == invite.org_id,
                    OrganizationInvite.email == invite.email,
                    OrganizationInvite.accepted_at == None,
                    OrganizationInvite.id != invite.id
                )
                .values(
                    accepted_at=datetime.now(timezone.utc),
                    accepted_email=user_email
                )
            )
            await self.session.execute(stmt_others)
            
            await self.session.flush()
            return True

        # 3. Create OrganizationUser record
        org_user = OrganizationUser(
            org_id=invite.org_id,
            user_id=user_id,
            role=invite.role
        )
        self.session.add(org_user)
        
        # 4. Mark invite as accepted
        # Also mark any other pending invites for this same email/org as accepted
        invite.accepted_at = datetime.now(timezone.utc)
        invite.accepted_email = user_email

        from sqlalchemy import update
        stmt_others = (
            update(OrganizationInvite)
            .where(
                OrganizationInvite.org_id == invite.org_id,
                OrganizationInvite.email == invite.email,
                OrganizationInvite.accepted_at == None,
                OrganizationInvite.id != invite.id
            )
            .values(
                accepted_at=datetime.now(timezone.utc),
                accepted_email=user_email
            )
        )
        await self.session.execute(stmt_others)
        
        await self.session.flush()
        logger.info(f"User {user_id} ({user_email}) accepted invite {invite_id} for org {invite.org_id} with role {invite.role}")
        return True
