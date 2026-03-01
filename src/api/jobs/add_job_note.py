import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from .models import JobNoteCreate

logger = logging.getLogger(__name__)

async def add_job_note(
    request: Request,
    job_id: uuid.UUID,
    body: JobNoteCreate,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Add a note to a job.
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
    job = await repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    note_id = await repo.add_job_note(
        job_id=job_id,
        user_id=user_id,
        content=body.content
    )
    
    await db.commit()
    
    # Trigger re-vectoring of the job to include new note
    from src.agents.jd_processor.run import run_jd_agent
    import asyncio
    asyncio.create_task(run_jd_agent(
        job_id=job_id,
        raw_text=job.get("raw_text"),
        org_id=org.id
    ))
    logger.info(f"Triggered re-vectoring for job {job_id} due to new note")
    
    return {
        "success": True,
        "note_id": str(note_id)
    }
