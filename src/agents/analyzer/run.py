import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

from ...agents.registry import get_analyzer_agent
from ...agents.utils import generate_thread_id
from ...constants import TASK_ANALYSIS, CONFIG_THREAD_ID_KEY
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, cancel_agent_task

logger = logging.getLogger(__name__)

# Track active analysis tasks
_active_analysis_tasks: Dict[str, asyncio.Task] = {}

async def run_analyzer_agent(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    job_data: Dict[str, Any],
    resume_data: Dict[str, Any],
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
            "analysis_id": None,
            "score": None,
            "score_breakdown": None,
            "scoring_reasoning": None,
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
            return bool(state.get("analysis_id"))

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
        return {"status": "cancelled", "thread_id": thread_id}
    finally:
        if _active_analysis_tasks.get(thread_id) == task:
            del _active_analysis_tasks[thread_id]

async def cancel_analyzer_agent(job_id: uuid.UUID, candidate_id: uuid.UUID):
    """Cancels a running analyzer agent task."""
    thread_id = generate_thread_id("analysis", job_id, str(candidate_id))
    return await cancel_agent_task(thread_id, _active_analysis_tasks, "ANALYZER_RUN")

def is_analysis_active(job_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
    """Check if an analysis processing task is currently active for a given job_id and candidate_id."""
    thread_id = generate_thread_id("analysis", job_id, str(candidate_id))
    return thread_id in _active_analysis_tasks
