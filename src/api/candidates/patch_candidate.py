import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from .models import CandidateUpdate

logger = logging.getLogger(__name__)

async def patch_candidate(
    request: Request,
    candidate_id: uuid.UUID,
    body: CandidateUpdate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Update a specific candidate by ID.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    repo = CandidateRepository(db)
    
    # Verify candidate exists and belongs to org
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if candidate.org_id and str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Not authorized to access this candidate")

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return {"success": True, "message": "No changes provided"}

    success = await repo.update_candidate(
        candidate_id=candidate_id,
        **update_data
    )
    
    if success:
        await db.commit()
        return {"success": True, "message": "Candidate updated successfully"}
    else:
        return {"success": False, "message": "Failed to update candidate"}
