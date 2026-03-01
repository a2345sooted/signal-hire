import uuid
from fastapi import Depends, Request, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository
from src.models.db_models import OrgRole

async def remove_organization_member(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Removes a member from an organization.
    Only OWNER and ADMIN can remove members.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)
    
    # Check if user has permission (OWNER or ADMIN)
    user_role = await repo.get_user_role_in_org(user_id, org_id)
    if not user_role or user_role not in [OrgRole.OWNER, OrgRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized to remove members from this organization")

    # Optional: Prevent removing the last OWNER or prevent OWNER from removing themselves if they are the only owner
    # For now, we'll keep it simple as requested.

    success = await repo.remove_organization_member(org_id, member_id)
    if not success:
        raise HTTPException(status_code=404, detail="Member record not found in this organization")

    await db.commit()

    return Response(status_code=204)
