import logging
from typing import Annotated, List, Optional
from fastapi import Depends, Request, HTTPException, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository

logger = logging.getLogger(__name__)

async def get_jobs(
    request: Request,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = Query(None),
    pay_type: Optional[str] = Query(None),
    salary_min: Optional[int] = Query(None),
    salary_max: Optional[int] = Query(None),
    hourly_min: Optional[int] = Query(None),
    hourly_max: Optional[int] = Query(None),
    employment_type: Optional[List[str]] = Query(None),
    work_arrangement: Optional[List[str]] = Query(None),
    offers_relocation: Optional[bool] = Query(None),
    no_candidates: Optional[bool] = Query(None)
):
    """
    Retrieve all jobs for the specified organization with filtering.
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

    logger.info(f"Fetching jobs for org: {org.name} ({org.id}) with filters: q={q}, pay_type={pay_type}, "
                f"salary_min={salary_min}, salary_max={salary_max}, hourly_min={hourly_min}, hourly_max={hourly_max}, "
                f"employment_type={employment_type}, work_arrangement={work_arrangement}, "
                f"offers_relocation={offers_relocation}, no_candidates={no_candidates}")
    repo = JobRepository(db)
    jobs = await repo.get_all_jobs(
        org_id=org.id,
        search_query=q,
        pay_type=pay_type,
        salary_min=salary_min,
        salary_max=salary_max,
        hourly_min=hourly_min,
        hourly_max=hourly_max,
        employment_types=employment_type,
        work_arrangements=work_arrangement,
        offers_relocation=offers_relocation,
        no_candidates=no_candidates
    )
    
    if jobs is None:
        logger.warning("JobRepository.get_all_jobs() returned None!")
        return []
    
    from src.agents.jd_processor.run import is_jd_processing_active
    
    formatted_jobs = []
    for job in jobs:
        # Check if a processing task is active for this job
        is_processing = await is_jd_processing_active(job["id"])
        
        # Determine markdown content - handle stuck placeholder
        markdown = job.get("markdown_content")
        if markdown and markdown != "SIGNAL_PROCESSING":
             # If we have actual content, we use it regardless of what is_jd_processing_active says
             markdown_text = markdown
        elif not is_processing and markdown == "SIGNAL_PROCESSING":
             # This job is stuck with a placeholder. We don't trigger processing here
             # to avoid heavy parallel background tasks in a list view, 
             # but we return the raw text instead of the placeholder.
             # The get_job (singular) endpoint will handle the actual re-triggering.
             markdown_text = job.get("raw_text") or ""
        else:
             markdown_text = "SIGNAL_PROCESSING" if is_processing else (markdown or job.get("raw_text") or "")
        
        resumes = []
        if job.get("resumes"):
            for resume in job["resumes"]:
                # For top candidates in get_jobs, we use the analysis status logic
                # We need a db session here, but get_jobs already has one.
                # However, repo.get_all_jobs already formatted these resumes slightly.
                # Let's see if we should enhance repo.get_all_jobs or do it here.
                # Given get_jobs is for a list view, we want to keep it efficient.
                
                resumes.append({
                    "id": resume.get("id"),
                    "original_filename": resume.get("name") or "Unknown",
                    "structured_data": {"rank": resume.get("rank")},
                    "analysis_id": resume.get("analysis_id"),
                    # We add these for consistency, though list view might not always use them
                    "analysis_status": "ready" if resume.get("analysis_id") else "pending",
                    "is_analysis_processing": False # Simplified for list view
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
            "markdown_text": markdown_text,
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
            "num_candidates": job.get("num_candidates", 0),
            "tags": ["Engineering", "Urgent"], # Stubbed
            "attached_candidates": top_candidates,
            "status": "open", # "open" or "closed"
            "owner_email": "user@example.com" # Stubbed
        })
    
    return formatted_jobs
