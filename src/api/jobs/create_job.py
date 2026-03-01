import logging
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from src.agents.jd_processor.run import run_jd_agent
from src.agents.utils import generate_thread_id, get_task_id
from .models import JobCreate

logger = logging.getLogger(__name__)

async def create_job(
    request: Request,
    body: JobCreate,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a job directly in the database.
    Triggers the AI agent asynchronously if raw_text is provided.
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

    # Only OWNER, ADMIN, or RECRUITER can create a job (all roles currently have this right)
    
    logger.info(f"Creating job: {body.title} for client: {body.client_name} for org: {org.name} ({org.id})")
    
    repo = JobRepository(db)
    
    # We use empty dict for structured_data as it's normally filled by agent
    # but the model now allows it to be null.
    job_id = await repo.create_job(
        title=body.title,
        client_name=body.client_name,
        raw_text=body.raw_text,
        org_id=org.id,
        location=body.location,
        work_arrangement=body.work_arrangement,
        hybrid_days_per_week=body.hybrid_days_per_week,
        pay_range_min=body.pay_range_min,
        pay_range_max=body.pay_range_max,
        pay_type=body.pay_type,
        employment_type=body.employment_type,
        offers_relocation=body.offers_relocation,
        structured_data={} 
    )
    
    await db.commit()
    
    # If raw_text was provided, trigger the JD agent asynchronously
    if body.raw_text:
        logger.info(f"Job created with raw_text for {job_id}. Clearing old content placeholders, registering task and triggering JD agent asynchronously.")
        
        # Clear any placeholders to ensure consistency
        await repo.update_job(
            job_id=job_id,
            markdown_content=None,
            structured_data=None
        )
        
        # Pre-register the task in the database so that immediate GET requests see SIGNAL_PROCESSING
        from src.repositories.processing_task_repository import ProcessingTaskRepository
        task_repo = ProcessingTaskRepository(db)
        
        # Use stable task_id derived from thread_id
        thread_id = generate_thread_id("jd", job_id)
        task_id = get_task_id(thread_id)
        
        await task_repo.create_task(
            task_id=task_id,
            task_type="jd",
            job_id=job_id,
            status="starting"
        )
        await db.commit()

        background_tasks.add_task(
            run_jd_agent, 
            raw_text=body.raw_text, 
            job_id=job_id, 
            org_id=org.id
        )
    
    return {
        "job_id": str(job_id)
    }
