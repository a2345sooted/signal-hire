import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

async def delete_job_note(
    request: Request,
    job_id: uuid.UUID,
    note_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific job note.
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

    repo = JobRepository(db)
    
    # 1. Verify Job existence and Org ownership
    job = await repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    # 2. Fetch the note and verify it belongs to the job and user
    note = await repo.get_job_note_by_id(note_id)
    if not note:
        logger.warning(f"Note {note_id} not found")
        raise HTTPException(status_code=404, detail="Note not found")
        
    if str(note.job_id) != str(job_id):
        logger.warning(f"Note {note_id} belongs to job {note.job_id}, not {job_id}")
        raise HTTPException(status_code=400, detail="Note does not belong to this job")
        
    if str(note.user_id) != str(user_id):
        logger.warning(f"Note {note_id} belongs to user {note.user_id}, not {user_id}")
        raise HTTPException(status_code=403, detail="You can only delete your own notes")

    # 3. Delete the note
    success = await repo.delete_job_note(note_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete note")
        
    await db.commit()
    
    return {
        "success": True,
        "note_id": str(note_id)
    }
