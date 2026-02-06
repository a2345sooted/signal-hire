import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

from ...agents.registry import get_analyzer_agent
from ...agents.utils import generate_thread_id
from ...constants import TASK_ANALYSIS, CONFIG_THREAD_ID_KEY
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, broadcast_agent_error, cancel_agent_task

logger = logging.getLogger(__name__)

# Track active analysis tasks
_active_analysis_tasks: Dict[str, asyncio.Task] = {}

async def run_analyzer_agent(
    job_id: uuid.UUID,
    resume_id: uuid.UUID,
    job_data: Dict[str, Any],
    resume_data: Dict[str, Any],
    thread_id_id: Optional[str] = None,
    personal_info_mismatch_question: Optional[str] = None
) -> Any:
    """
    Runs the full analyzer agent.
    Returns the final state dictionary.
    """
    thread_id = generate_thread_id("analysis", job_id, thread_id_id)
    log_tag = "ANALYZER_RUN"
    logger.info(f"[{log_tag}] [{thread_id}] Starting analyzer agent...")
    
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
            "resume_id": str(resume_id),
            "job_id": str(job_id),
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

        async def error_broadcaster(e: Exception):
            await broadcast_agent_error(
                job_id=job_id,
                thread_id=thread_id,
                error=e,
                log_tag=log_tag,
                extra_data={
                    "resume_id": str(resume_id),
                    "completed": False
                }
            )

        result = await run_agent_with_retries(
            agent=get_analyzer_agent(),
            initial_state=initial_state,
            config=config,
            log_tag=log_tag,
            completion_check=completion_check,
            error_broadcaster=error_broadcaster
        )

        # Broadcast completion
        from ...api.ws.manager import manager
        import json
        logger.info(f"[{log_tag}] [{thread_id}] Broadcasting analysis completion for resume_id: {resume_id}")
        await manager.broadcast_to_job(
            json.dumps({
                "status": "Success",
                "message": "Resume analysis completed successfully",
                "completed": True,
                "resume_id": str(resume_id)
            }),
            str(job_id)
        )
        return result

    except asyncio.CancelledError:
        return {"status": "cancelled", "thread_id": thread_id}
    finally:
        if _active_analysis_tasks.get(thread_id) == task:
            del _active_analysis_tasks[thread_id]

async def cancel_analyzer_agent(job_id: uuid.UUID):
    """Cancels a running analyzer agent task."""
    thread_id = generate_thread_id("analysis", job_id)
    return await cancel_agent_task(thread_id, _active_analysis_tasks, "ANALYZER_RUN")
