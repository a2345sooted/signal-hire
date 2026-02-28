import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.candidate_repository import CandidateRepository

logger = logging.getLogger(__name__)

async def get_analysis(
    analysis_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve a specific analysis by ID, including candidate_id and job markdown.
    """
    logger.info(f"Fetching analysis: {analysis_id}")
    repo = AnalysisRepository(db)
    analysis_data = await repo.get_analysis_by_id(analysis_id)
    if not analysis_data:
        return {"success": False, "message": "Analysis not found"}
    
    candidate_repo = CandidateRepository(db)
    candidate = await candidate_repo.get_candidate_by_id(uuid.UUID(analysis_data["candidate_id"]))
    if not candidate:
        return {"success": False, "message": "Candidate not found for analysis"}
    
    # We might need to find a resume for this candidate/job to get more info (like email, filename)
    resume_repo = ResumeRepository(db)
    resumes = await resume_repo.get_resumes_by_job_id(uuid.UUID(analysis_data["job_id"]))
    # Filter by candidate_id
    candidate_resumes = [r for r in resumes if str(r.candidate_id) == analysis_data["candidate_id"]]
    resume = candidate_resumes[0] if candidate_resumes else None
    
    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(uuid.UUID(analysis_data["job_id"]))
    if not job:
         return {"success": False, "message": "Job not found for analysis"}
    
    return {
        "analysis": analysis_data["content"],
        "candidate_id": analysis_data["candidate_id"],
        "candidate_name": candidate.get("name") or "Unknown",
        "resume_id": str(resume.id) if resume else None,
        "resume_name": resume.original_filename if resume else "Unknown",
        "resume_email": (resume.structured_data or {}).get("contact", {}).get("email") if resume else "No email",
        "resume_structured_data": resume.structured_data if resume else {},
        "job_title": job.get("title") or "Untitled Job",
        "job_markdown": job.get("markdown_content") or job.get("raw_text") or ""
    }
