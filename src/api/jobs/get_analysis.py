import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.job_repository import JobRepository
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository
from src.repositories.candidate_repository import CandidateRepository
from src.agents.analyzer.run import is_analysis_active

logger = logging.getLogger(__name__)

async def get_analysis(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve analysis for a specific job and candidate.
    """
    logger.info(f"Fetching analysis for job: {job_id}, candidate: {candidate_id}")
    
    analysis_repo = AnalysisRepository(db)
    analysis = await analysis_repo.get_analysis_for_candidate_job(candidate_id, job_id)
    
    # Check if analysis is missing OR in a processing state
    is_processing = False
    
    # If no DB record or if it's explicitly 'processing', we check memory tasks
    from src.agents.resume_processor.run import is_resume_processing_active
    if is_resume_processing_active(candidate_id=candidate_id):
        is_processing = True
    elif analysis:
        content = analysis.get("content", {})
        if content.get("status") == "processing":
            is_processing = True
    else:
        # If no DB record, check memory registry for analyzer task
        if is_analysis_active(job_id, candidate_id):
            is_processing = True
            
    if is_processing:
        return {
            "success": True,
            "status": "processing",
            "analysis": "SIGNAL_PROCESSING"
        }
        
    if not analysis:
        return {
            "success": False,
            "message": "Analysis not found",
            "status": "pending"
        }
    
    return {
        "success": True,
        "analysis": analysis["content"],
        "candidate_id": str(candidate_id),
        "job_id": str(job_id),
        "status": "completed"
    }
