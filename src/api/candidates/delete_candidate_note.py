import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

async def delete_candidate_note(
    request: Request,
    candidate_id: uuid.UUID,
    note_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific candidate note.
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
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    repo = CandidateRepository(db)
    
    # 1. Fetch the note and verify it belongs to the candidate and user
    note = await repo.get_note_by_id(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
        
    if note.candidate_id != candidate_id:
        raise HTTPException(status_code=400, detail="Note does not belong to this candidate")
        
    if note.user_id != user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own notes")

    # 2. Verify candidate belongs to the org
    from src.models.db_models import Candidate
    from sqlalchemy.future import select
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
        
    if str(candidate.org_id) != str(org.id):
        raise HTTPException(status_code=403, detail="Candidate does not belong to this organization")

    # 3. Delete the note
    success = await repo.delete_note(note_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete note")
        
    await db.commit()
    
    return {
        "success": True,
        "note_id": str(note_id)
    }
