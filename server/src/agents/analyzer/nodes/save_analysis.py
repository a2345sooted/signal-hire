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
    resume_id = state.get("resume_id")
    job_id = state.get("job_id")
    
    if not resume_id or not job_id:
        logger.error("[ANALYZER_AGENT] Missing resume_id or job_id for saving analysis")
        return state

    content = {
        "score": state.get("score"),
        "score_breakdown": state.get("score_breakdown"),
        "scoring_reasoning": state.get("scoring_reasoning"),
        "major_hits": state.get("major_hits"),
        "minor_hits": state.get("minor_hits"),
        "major_gaps": state.get("major_gaps"),
        "minor_gaps": state.get("minor_gaps"),
        "messages": state.get("messages"),
    }

    try:
        # Broadcast status
        from ....api.ws.manager import manager
        import json
        if job_id:
            await manager.broadcast_to_job(
                json.dumps({
                    "status": "Saving",
                    "message": "Storing analysis results to database...",
                    "resume_id": str(resume_id),
                    "completed": False
                }),
                str(job_id)
            )

        async with AsyncSessionLocal() as db:
            repo = AnalysisRepository(db)
            analysis_id = await repo.create_analysis(
                resume_id=uuid.UUID(resume_id),
                content=content
            )
            await db.commit()
            logger.info(f"[ANALYZER_AGENT] Analysis saved with ID: {analysis_id}")
            return {"analysis_id": analysis_id}
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] Failed to save analysis: {str(e)}", exc_info=True)
        return state
