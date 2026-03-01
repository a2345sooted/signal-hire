import logging
import uuid
import hashlib
import json

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
    job_data = state.get("job_data", {})
    
    if not candidate_id or not job_id:
        logger.error("[ANALYZER_AGENT] Missing candidate_id or job_id for saving analysis")
        return state

    # Calculate hashes for JD and Details
    raw_jd = job_data.get("raw_text", "")
    details = job_data.get("details", {})
    
    jd_hash = hashlib.sha256(raw_jd.encode()).hexdigest() if raw_jd else None
    details_hash = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest() if details else None

    content = {
        "score": state.get("score"),
        "score_breakdown": state.get("score_breakdown"),
        # Separate hits/gaps are deprecated in favor of being included in the markdown message.
        # We keep them as empty lists for backward compatibility if needed.
        "major_hits": [],
        "minor_hits": [],
        "major_gaps": [],
        "minor_gaps": [],
        "message": state.get("messages", [""])[-1] if state.get("messages") else "",
        "hiring_notes": state.get("hiring_notes"),
        "status": "completed"
    }

    try:
        async with AsyncSessionLocal() as db:
            repo = AnalysisRepository(db)
            
            # Use candidate_id, job_id, and resume_id as strings for safety then cast to UUID
            try:
                c_id = uuid.UUID(str(candidate_id))
                j_id = uuid.UUID(str(job_id))
                r_id = uuid.UUID(str(resume_id)) if resume_id else None
            except ValueError as ve:
                logger.error(f"[ANALYZER_AGENT] Invalid UUID format in state: candidate_id={candidate_id}, job_id={job_id}, resume_id={resume_id}")
                return {"analysis_id": None} # Signal failure to completion check

            logger.info(f"[ANALYZER_AGENT] Checking for existing analysis. candidate_id={c_id}, job_id={j_id}, resume_id={r_id}")
            # Check for existing skeleton analysis
            existing = await repo.get_analysis_for_candidate_job_resume(
                candidate_id=c_id,
                job_id=j_id,
                resume_id=r_id
            )
            
            if existing:
                logger.info(f"[ANALYZER_AGENT] Updating existing analysis {existing['id']}")
                await repo.update_analysis(
                    analysis_id=uuid.UUID(str(existing['id'])),
                    content=content,
                    resume_id=r_id,
                    jd_hash=jd_hash,
                    details_hash=details_hash
                )
                analysis_id = existing['id']
            else:
                logger.info("[ANALYZER_AGENT] Creating new analysis record")
                analysis_id = await repo.create_analysis(
                    candidate_id=c_id,
                    job_id=j_id,
                    content=content,
                    resume_id=r_id,
                    jd_hash=jd_hash,
                    details_hash=details_hash
                )
            
            await db.commit()
            logger.info(f"[ANALYZER_AGENT] Analysis saved with ID: {analysis_id}")
            # Return ONLY the updated field to merge into state
            return {"analysis_id": uuid.UUID(str(analysis_id))}
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] Failed to save analysis: {str(e)}", exc_info=True)
        # We must return SOMETHING that doesn't wipe the state, but we also need to signal failure
        # to the completion check if we want it to retry. 
        # By returning a state with analysis_id explicitly None, we ensure the completion check fails.
        return {"analysis_id": None}
