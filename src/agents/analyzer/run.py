import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List

from ...agents.registry import get_analyzer_agent
from ...agents.utils import generate_thread_id
from ...constants import TASK_ANALYSIS, CONFIG_THREAD_ID_KEY
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, cancel_agent_task

from ...database import AsyncSessionLocal
from ...repositories.processing_task_repository import ProcessingTaskRepository

logger = logging.getLogger(__name__)

# Track active analysis tasks
_active_analysis_tasks: Dict[str, asyncio.Task] = {}

async def run_analyzer_agent(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    job_data: Dict[str, Any],
    resume_data: Dict[str, Any],
    candidate_notes: Optional[List[Dict[str, Any]]] = None,
    candidate_location: Optional[str] = None,
    candidate_metadata: Optional[Dict[str, Any]] = None,
    thread_id_id: Optional[str] = None,
    personal_info_mismatch_question: Optional[str] = None,
    org_id: Optional[uuid.UUID] = None
) -> Any:
    """
    Runs the full analyzer agent.
    Returns the final state dictionary.
    """
    thread_id = generate_thread_id("analysis", job_id, thread_id_id or str(candidate_id))
    log_tag = "ANALYZER_RUN"
    logger.info(f"[{log_tag}] [{thread_id}] Starting analyzer agent for candidate {candidate_id}...")
    
    # Check if this is already running
    existing_result = await handle_active_task(thread_id, _active_analysis_tasks, log_tag)
    if existing_result is not None:
        return existing_result

    task = manage_active_task(thread_id, _active_analysis_tasks)

    try:
        from ...agents.analyzer.state import AnalyzerMetadata, AnalyzerState
        
        initial_metadata: AnalyzerMetadata = {
            "task_type": TASK_ANALYSIS,
            "status": "starting"
        }
        
        initial_state: AnalyzerState = {
            "thread_id": thread_id,
            "candidate_id": str(candidate_id),
            "job_id": str(job_id),
            "resume_id": str(resume_data.get("resume_id")) if resume_data.get("resume_id") else None,
            "org_id": org_id,
            "resume_data": resume_data,
            "job_data": job_data,
            "candidate_notes": candidate_notes,
            "candidate_location": candidate_location,
            "candidate_metadata": candidate_metadata,
            "analysis_id": None,
            "score": None,
            "score_breakdown": None,
            "major_hits": [],
            "minor_hits": [],
            "major_gaps": [],
            "minor_gaps": [],
            "messages": [],
            "personal_info_mismatch_question": personal_info_mismatch_question,
            "metadata": initial_metadata
        }
        
        config = {"configurable": {CONFIG_THREAD_ID_KEY: thread_id}}

        def completion_check(state: AnalyzerState) -> bool:
            # We check if analysis_id is present, which is set by save_analysis_node.
            # If it's missing after the agent run, it means the agent failed to reach the end or failed to save.
            analysis_id = state.get("analysis_id")
            has_analysis_id = bool(analysis_id)
            if not has_analysis_id:
                 logger.warning(f"[{log_tag}] [{thread_id}] Completion check failed: analysis_id is missing from state. Value: {analysis_id} (type: {type(analysis_id)})")
                 # Check if we have core results but just failed to save
                 if state.get("score") is not None and state.get("major_hits"):
                     logger.info(f"[{log_tag}] [{thread_id}] Core results exist, but analysis_id is missing. Likely a save failure.")
            return has_analysis_id

        result = await run_agent_with_retries(
            agent=get_analyzer_agent(),
            initial_state=initial_state,
            config=config,
            log_tag=log_tag,
            completion_check=completion_check,
            error_broadcaster=None
        )

        return result

    except asyncio.CancelledError:
        logger.info(f"[{log_tag}] [{thread_id}] Analyzer agent task cancelled.")
        return {"status": "cancelled", "thread_id": thread_id}
    except Exception as e:
        logger.error(f"[{log_tag}] [{thread_id}] Analyzer agent failed with error: {str(e)}", exc_info=True)
        # Ensure we update the task status to failed if we have the task_id
        from ...agents.utils import get_task_id
        task_id = get_task_id(thread_id)
        if task_id:
            try:
                async with AsyncSessionLocal() as db:
                    repo = ProcessingTaskRepository(db)
                    await repo.update_task(task_id, status="failed", error_message=str(e))
                    await db.commit()
            except Exception as db_err:
                logger.error(f"[{log_tag}] [{thread_id}] Failed to update task status to failed: {str(db_err)}")
        return {"status": "failed", "error": str(e), "thread_id": thread_id}
    finally:
        if _active_analysis_tasks.get(thread_id) == task:
            del _active_analysis_tasks[thread_id]

async def cancel_analyzer_agent(job_id: uuid.UUID, candidate_id: uuid.UUID, resume_id: Optional[uuid.UUID] = None):
    """Cancels a running analyzer agent task."""
    thread_id = generate_thread_id("analysis", job_id, str(resume_id or candidate_id))
    return await cancel_agent_task(thread_id, _active_analysis_tasks, "ANALYZER_RUN")

async def is_analysis_active(job_id: uuid.UUID, candidate_id: uuid.UUID, thread_id_id: Optional[str] = None) -> bool:
    """Check if an analysis processing task is currently active for a given job_id and candidate_id."""
    # We use memory check first for speed
    thread_id = generate_thread_id("analysis", job_id, thread_id_id or str(candidate_id))
    if thread_id in _active_analysis_tasks and not _active_analysis_tasks[thread_id].done():
        return True

    # Fallback to DB check
    async with AsyncSessionLocal() as db:
        repo = ProcessingTaskRepository(db)
        # Note: repository uses job_id and candidate_id which is broader, but safer
        return await repo.is_task_active(task_type=TASK_ANALYSIS, job_id=job_id, candidate_id=candidate_id)
