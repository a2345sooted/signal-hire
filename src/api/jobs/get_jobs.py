import logging
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

async def get_jobs(
    request: Request,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve all jobs for the specified organization.
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

    logger.info(f"Fetching all jobs for org: {org.name} ({org.id})")
    repo = JobRepository(db)
    jobs = await repo.get_all_jobs(org_id=org.id)
    
    if jobs is None:
        logger.warning("JobRepository.get_all_jobs() returned None!")
        return []
    
    from src.agents.jd_processor.run import is_jd_processing_active
    
    formatted_jobs = []
    for job in jobs:
        # Check if a processing task is active for this job
        is_processing = await is_jd_processing_active(job["id"])
        
        resumes = []
        if job.get("resumes"):
            for resume in job["resumes"]:
                resumes.append({
                    "id": resume.get("id"),
                    "original_filename": resume.get("name") or "Unknown",
                    "structured_data": {"rank": resume.get("rank")},
                    "analysis_id": resume.get("analysis_id")
                })
        
        # Sort resumes by rank to get top candidates
        sorted_resumes = sorted(resumes, key=lambda x: x["structured_data"].get("rank") or 0, reverse=True)
        top_candidates = sorted_resumes[:3] # Show top 3 candidates

        # Construct pay string
        pay_min = job.get("pay_range_min")
        pay_max = job.get("pay_range_max")
        pay_str = None
        if pay_min is not None and pay_max is not None:
            pay_str = f"${pay_min:,} - ${pay_max:,}"
        elif pay_min is not None:
            pay_str = f"${pay_min:,}+"
        elif pay_max is not None:
            pay_str = f"Up to ${pay_max:,}"

        formatted_jobs.append({
            "id": str(job["id"]),
            "title": job.get("title") or "Untitled Job",
            "client_name": job.get("client_name"),
            "markdown_text": "SIGNAL_PROCESSING" if is_processing else (job.get("markdown_content") or job.get("raw_text") or ""),
            "raw_text": job.get("raw_text") or "",
            "location": job.get("location"),
            "work_arrangement": job.get("work_arrangement"),
            "hybrid_days_per_week": job.get("hybrid_days_per_week"),
            "pay_range_min": job.get("pay_range_min"),
            "pay_range_max": job.get("pay_range_max"),
            "pay": pay_str,
            "pay_type": job.get("pay_type"),
            "employment_type": job.get("employment_type"),
            "offers_relocation": job.get("offers_relocation") or False,
            "details": job.get("details"),
            "created_at": job.get("created_at"),
            "resumes": resumes,
            "resume_count": len(resumes),
            "num_candidates": len(resumes), # Stubbed but using actual count
            "tags": ["Engineering", "Urgent"], # Stubbed
            "attached_candidates": top_candidates,
            "status": "open", # "open" or "closed"
            "owner_email": "user@example.com" # Stubbed
        })
    
    return formatted_jobs
