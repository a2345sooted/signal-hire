import logging
import uuid
from typing import Annotated
from datetime import datetime
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from src.agents.jd_processor.run import is_jd_processing_active
from .models import JobResponse

logger = logging.getLogger(__name__)

async def get_job(
    request: Request,
    job_id: uuid.UUID,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific job by ID for the specified organization.
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

    logger.info(f"Fetching job: {job_id} for org: {org.slug}")
    repo = JobRepository(db)
    job = await repo.get_job_by_id(job_id)
    if not job:
        return {"success": False, "message": "Job not found"}
    
    # Verify job belongs to this org
    if job.get("org_id") and str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")
    
    # Check if a processing task is active for this job
    is_processing = is_jd_processing_active(job_id)
    
    # Use the JobResponse model to ensure all fields are returned
    job_data = {
        "id": str(job["id"]),
        "title": job.get("title") or "Untitled Job",
        "client_name": job.get("client_name"),
        "raw_text": job.get("raw_text"),
        "markdown_text": "SIGNAL_PROCESSING" if is_processing else (job.get("markdown_content") or job.get("raw_text") or ""),
        "location": job.get("location"),
        "work_arrangement": job.get("work_arrangement"),
        "hybrid_days_per_week": job.get("hybrid_days_per_week"),
        "pay_range_min": job.get("pay_range_min"),
        "pay_range_max": job.get("pay_range_max"),
        "pay_type": job.get("pay_type"),
        "employment_type": job.get("employment_type"),
        "offers_relocation": job.get("offers_relocation") or False,
        "created_at": job["created_at"].isoformat() if isinstance(job.get("created_at"), datetime) else job.get("created_at"),
        "notes": job.get("notes") or [],
        "num_candidates": 0,
        "attached_candidates": job.get("attached_candidates") or [],
        "recommended_candidates": job.get("recommended_candidates") or [],
    }
    
    # Construct pay string for consistency
    pay_min = job.get("pay_range_min")
    pay_max = job.get("pay_range_max")
    if pay_min is not None and pay_max is not None:
        job_data["pay"] = f"${pay_min:,} - ${pay_max:,}"
    elif pay_min is not None:
        job_data["pay"] = f"${pay_min:,}+"
    elif pay_max is not None:
        job_data["pay"] = f"Up to ${pay_max:,}"

    return JobResponse.model_validate(job_data)
