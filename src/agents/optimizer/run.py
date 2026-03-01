import asyncio
import logging
import uuid
from typing import Dict, Any, Optional

from ...agents.registry import get_optimizer_agent
from ...agents.utils import generate_thread_id
from ...constants import TASK_OPTIMIZER, CONFIG_THREAD_ID_KEY
from ...agents.base_runner import run_agent_with_retries, handle_active_task, manage_active_task, cancel_agent_task

from ...database import AsyncSessionLocal
from ...repositories.processing_task_repository import ProcessingTaskRepository

logger = logging.getLogger(__name__)

# Track active optimizer tasks
_active_optimizer_tasks: Dict[str, asyncio.Task] = {}

async def run_optimizer_agent(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    resume_id: uuid.UUID,
    job_data: Dict[str, Any],
    resume_data: Dict[str, Any],
    analysis_data: Dict[str, Any],
    thread_id_id: Optional[str] = None,
    org_id: Optional[uuid.UUID] = None
) -> Any:
    """
    Runs the full optimizer agent.
    Returns the final state dictionary.
    """
    thread_id = generate_thread_id("optimizer", job_id, thread_id_id or str(candidate_id))
    log_tag = "OPTIMIZER_RUN"
    logger.info(f"[{log_tag}] [{thread_id}] Starting optimizer agent for candidate {candidate_id}...")
    
    # Check if this is already running
    existing_result = await handle_active_task(thread_id, _active_optimizer_tasks, log_tag)
    if existing_result is not None:
        return existing_result

    task = manage_active_task(thread_id, _active_optimizer_tasks)

    try:
        from ...agents.optimizer.state import OptimizerMetadata, OptimizerState
        
        initial_metadata: OptimizerMetadata = {
            "task_type": TASK_OPTIMIZER,
            "status": "starting"
        }
        
        initial_state: OptimizerState = {
            "thread_id": thread_id,
            "candidate_id": str(candidate_id),
            "job_id": str(job_id),
            "resume_id": str(resume_id),
            "org_id": org_id,
            "job_data": job_data,
            "resume_data": resume_data,
            "analysis_data": analysis_data,
            "optimization_plan": None,
            "optimized_resume": None,
            "new_resume_id": None,
            "messages": [],
            "metadata": initial_metadata
        }
        
        config = {"configurable": {CONFIG_THREAD_ID_KEY: thread_id}}

        def completion_check(state: OptimizerState) -> bool:
            return bool(state.get("new_resume_id"))

        result = await run_agent_with_retries(
            agent=get_optimizer_agent(),
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
        if _active_optimizer_tasks.get(thread_id) == task:
            del _active_optimizer_tasks[thread_id]

async def cancel_optimizer_agent(job_id: uuid.UUID, candidate_id: uuid.UUID, resume_id: Optional[uuid.UUID] = None):
    """Cancels a running optimizer agent task."""
    thread_id = generate_thread_id("optimizer", job_id, str(resume_id or candidate_id))
    return await cancel_agent_task(thread_id, _active_optimizer_tasks, "OPTIMIZER_RUN")

async def is_optimizer_active(job_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
    """Check if an optimizer processing task is currently active for a given job_id and candidate_id."""
    async with AsyncSessionLocal() as db:
        repo = ProcessingTaskRepository(db)
        return await repo.is_task_active(task_type="optimizer", job_id=job_id, candidate_id=candidate_id)
