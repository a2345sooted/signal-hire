import logging
import uuid

from langchain_core.runnables import RunnableConfig

from ....agents.analyzer.state import AnalyzerState
from ....database import AsyncSessionLocal
from ....repositories.analysis_repository import AnalysisRepository

logger = logging.getLogger(__name__)

async def save_analysis_node(state: AnalyzerState, config: RunnableConfig = None):
    """
    Saves the analysis results to the database.
    """
    candidate_id = state.get("candidate_id")
    job_id = state.get("job_id")
    resume_id = state.get("resume_id")
    
    if not candidate_id or not job_id:
        logger.error("[ANALYZER_AGENT] Missing candidate_id or job_id for saving analysis")
        return state

    content = {
        "score": state.get("score"),
        "score_breakdown": state.get("score_breakdown"),
        "scoring_reasoning": state.get("scoring_reasoning"),
        "major_hits": state.get("major_hits"),
        "minor_hits": state.get("minor_hits"),
        "major_gaps": state.get("major_gaps"),
        "minor_gaps": state.get("minor_gaps"),
        "message": state.get("messages", [""])[0] if state.get("messages") else "",
    }

    try:
        async with AsyncSessionLocal() as db:
            repo = AnalysisRepository(db)
            
            # Check for existing skeleton analysis
            existing = await repo.get_analysis_for_candidate_job_resume(
                candidate_id=uuid.UUID(candidate_id),
                job_id=uuid.UUID(job_id),
                resume_id=uuid.UUID(resume_id) if resume_id else None
            )
            
            if existing:
                logger.info(f"[ANALYZER_AGENT] Updating existing analysis {existing['id']}")
                await repo.update_analysis(
                    analysis_id=uuid.UUID(existing['id']),
                    content=content,
                    resume_id=uuid.UUID(resume_id) if resume_id else None
                )
                analysis_id = existing['id']
            else:
                logger.info("[ANALYZER_AGENT] Creating new analysis record")
                analysis_id = await repo.create_analysis(
                    candidate_id=uuid.UUID(candidate_id),
                    job_id=uuid.UUID(job_id),
                    content=content,
                    resume_id=uuid.UUID(resume_id) if resume_id else None
                )
            
            await db.commit()
            logger.info(f"[ANALYZER_AGENT] Analysis saved with ID: {analysis_id}")
            return {"analysis_id": analysis_id}
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] Failed to save analysis: {str(e)}", exc_info=True)
        return state
