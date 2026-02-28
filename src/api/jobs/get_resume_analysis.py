import logging
import uuid
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.resume_repository import ResumeRepository
from src.repositories.analysis_repository import AnalysisRepository

logger = logging.getLogger(__name__)

async def get_resume_analysis(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieve analysis for a specific resume by finding the candidate it belongs to.
    """
    logger.info(f"Fetching analysis for resume: {resume_id}")
    resume_repo = ResumeRepository(db)
    resume = await resume_repo.get_resume_by_id(resume_id)
    if not resume or not resume.get("candidate_id"):
        return {"success": False, "message": "Resume or candidate not found"}
    
    candidate_id = uuid.UUID(resume["candidate_id"])
    analysis_repo = AnalysisRepository(db)
    analysis = await analysis_repo.get_latest_analysis_for_candidate(candidate_id)
    
    if not analysis:
        return {"success": False, "message": "Analysis not found for candidate"}
        
    return analysis
