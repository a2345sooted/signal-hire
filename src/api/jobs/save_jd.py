import asyncio
import logging
import uuid
from typing import Annotated
from fastapi import Form, Depends, BackgroundTasks, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.jd_processor.run import run_jd_agent
from src.database import get_db
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

async def save_jd(
    request: Request,
    job_description: Annotated[str, Form(...)],
    background_tasks: BackgroundTasks,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Handle job description save requests.
    Kicks off the processor agent. Job record is created only after processing is complete.
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
    
    logger.info(f"Received save JD request for org: {org.slug}")
    
    # Generate a job_id for tracking, but don't save to DB yet
    job_id = uuid.uuid4()
    
    logger.info(f"Generated temporary job_id: {job_id}. Starting agent...")
    
    # Kick off the agent in the background
    background_tasks.add_task(run_jd_agent, raw_text=job_description, job_id=job_id, org_id=org.id)
    
    return {
        "success": True,
        "message": "Job description processing started",
        "job_id": str(job_id)
    }
