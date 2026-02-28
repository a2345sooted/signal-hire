import uuid
from typing import Annotated
from fastapi import Depends, Request, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository
from src.api.candidates.models import NoteCreate

async def add_candidate_note(
    request: Request,
    candidate_id: uuid.UUID,
    body: NoteCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to a candidate.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    candidate_repo = CandidateRepository(db)
    # Ideally check if candidate exists and belongs to the org
    candidate = await candidate_repo.get_candidate_by_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    note_id = await candidate_repo.add_note(
        candidate_id=candidate_id,
        user_id=user_id,
        content=body.content
    )
    
    await db.commit()
    
    return {
        "success": True,
        "note_id": note_id
    }
