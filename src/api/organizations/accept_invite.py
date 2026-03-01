import uuid
from fastapi import Depends, Request, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository

async def accept_invite(
    invite_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Accepts an organization invitation for the current authenticated user.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    repo = OrganizationRepository(db)
    
    # 1. Fetch invite to check email if needed (optional security check)
    invite = await repo.get_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # 2. Accept invite
    success = await repo.accept_invite(invite_id, user_id)
    if not success:
        # Check why it failed - already accepted or expired or doesn't exist (already checked)
        from datetime import datetime, timezone
        if invite.accepted_at:
             raise HTTPException(status_code=400, detail="Invitation already accepted")
        if invite.expires_at < datetime.now(timezone.utc):
             raise HTTPException(status_code=410, detail="Invitation expired")
        
        raise HTTPException(status_code=400, detail="Could not accept invitation")

    await db.commit()
    
    return Response(status_code=204)
