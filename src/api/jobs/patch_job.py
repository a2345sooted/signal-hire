import logging
import uuid
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from src.agents.jd_processor.run import run_jd_agent
from .models import JobUpdate

logger = logging.getLogger(__name__)

async def patch_job(
    request: Request,
    job_id: uuid.UUID,
    body: JobUpdate,
    x_org_slug: Annotated[str, Header()],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a specific job by ID for the specified organization.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization with slug '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Verify job belongs to this org
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    logger.info(f"Patching job: {job_id} for org: {org.slug}")
    
    # We only update fields that were provided in the request body
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        return {"success": True, "message": "No changes provided"}

    # Map 'title' in JobUpdate to 'title' in repo.update_job
    success = await repo.update_job(
        job_id=job_id,
        **update_data
    )
    
    if success:
        await db.commit()
        
        # If raw_text was updated and is different, trigger the JD agent
        new_raw_text = update_data.get("raw_text")
        if new_raw_text and new_raw_text != job.get("raw_text"):
            logger.info(f"Job raw_text updated for {job_id}. Triggering JD agent asynchronously.")
            background_tasks.add_task(
                run_jd_agent, 
                raw_text=new_raw_text, 
                job_id=job_id, 
                org_id=org.id
            )
            
        return {"success": True, "message": f"Job {job_id} updated successfully"}
    else:
        return {"success": False, "message": "Failed to update job"}
