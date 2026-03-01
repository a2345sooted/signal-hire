import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, Protocol, TypeVar, Mapping

from .utils import get_checkpoint_config, extract_uuid_from_thread_id, get_task_id
from ..database import AsyncSessionLocal
from ..repositories.processing_task_repository import ProcessingTaskRepository

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Mapping[str, Any])

class Agent(Protocol):
    async def ainvoke(self, input: Mapping[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]: ...
    async def aget_state(self, config: Dict[str, Any]) -> Any: ...

async def run_agent_with_retries(
    agent: Agent,
    initial_state: T,
    config: Dict[str, Any],
    log_tag: str,
    max_retries: int = 3,
    completion_check: Optional[Callable[[T], bool]] = None,
    error_broadcaster: Optional[Callable[[Exception], Awaitable[None]]] = None
) -> T:
    """
    Common runner for agents with retry logic and checkpoint resuming.
    """
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")
    start_time = time.time()
    attempt = 1
    
    # 1. Register task in DB
    task_id = get_task_id(thread_id)
    if task_id:
        try:
            async with AsyncSessionLocal() as db:
                repo = ProcessingTaskRepository(db)
                # Try to determine task_type from thread_id prefix
                task_type = "unknown"
                if thread_id.startswith("jd_"): task_type = "jd"
                elif thread_id.startswith("resume_"): task_type = "resume"
                elif thread_id.startswith("analysis_"): task_type = "analysis"
                elif thread_id.startswith("optimizer_"): task_type = "optimizer"
                
                # Determine associated IDs from initial_state
                job_id = None
                if initial_state.get("job_id"):
                    job_id = uuid.UUID(str(initial_state["job_id"]))
                
                candidate_id = None
                if initial_state.get("candidate_id"):
                    candidate_id = uuid.UUID(str(initial_state["candidate_id"]))
                
                resume_id = None
                if initial_state.get("resume_id"):
                    resume_id = uuid.UUID(str(initial_state["resume_id"]))

                await repo.create_task(
                    task_id=task_id,
                    task_type=task_type,
                    job_id=job_id,
                    candidate_id=candidate_id,
                    resume_id=resume_id,
                    status="starting"
                )
                await db.commit()
        except Exception as e:
            logger.error(f"[{log_tag}] [{thread_id}] Failed to create processing task record: {str(e)}")

    while attempt <= max_retries:
        try:
            # 2. Check current state if possible
            state = None
            is_finished = False
            try:
                checkpoint_config = get_checkpoint_config(thread_id)
                saved_state = await agent.aget_state(checkpoint_config)
                if saved_state and saved_state.values:
                    state = saved_state.values
                    # Check if the thread is finished (no next steps)
                    is_finished = not getattr(saved_state, "next", None)
            except Exception as e:
                logger.warning(f"[{log_tag}] [{thread_id}] Failed to get state from checkpointer: {str(e)}")

            if attempt > 1:
                logger.info(f"[{log_tag}] [{thread_id}] 🔄 Retrying agent (attempt {attempt}/{max_retries})")
                
                if state:
                    # If we have a completion check and it passes for the checkpoint state,
                    # we still want to make sure the side-effects happen.
                    # LangGraph naturally resumes and runs any remaining nodes.
                    logger.info(f"[{log_tag}] [{thread_id}] Found existing state in checkpointer. Resuming to ensure all nodes (including saving) complete.")
                    
                    if task_id:
                        try:
                            async with AsyncSessionLocal() as db:
                                repo = ProcessingTaskRepository(db)
                                await repo.update_task(task_id, status="processing")
                                await db.commit()
                        except: pass
                    
                    # If finished and completion check passes, we might need to RE-RUN if results are missing from DB
                    # But run_agent_with_retries doesn't know about the DB results, only the caller does (via completion_check)
                    final_state = await agent.ainvoke(None, config=config)
                else:
                    logger.info(f"[{log_tag}] [{thread_id}] No checkpoint found, restarting.")
                    if task_id:
                        try:
                            async with AsyncSessionLocal() as db:
                                repo = ProcessingTaskRepository(db)
                                await repo.update_task(task_id, status="processing")
                                await db.commit()
                        except: pass
                    final_state = await agent.ainvoke(initial_state, config=config)
            else:
                # First attempt
                if state:
                    if is_finished and completion_check and completion_check(state):
                        # If finished and completion check already passes, it means we were called
                        # because something is missing from the production database despite the agent
                        # thinking it's done. We must FORCE a re-run of the saving node or the whole thing.
                        # Since it's finished, ainvoke(None) is a no-op.
                        # We force a re-run from the start by using initial_state.
                        logger.info(f"[{log_tag}] [{thread_id}] Agent state is already finished and valid, but re-triggered. Forcing restart to ensure DB consistency.")
                        final_state = await agent.ainvoke(initial_state, config=config)
                    else:
                        logger.info(f"[{log_tag}] [{thread_id}] Found existing state in checkpointer. Using it to resume.")
                        
                        if task_id:
                            try:
                                async with AsyncSessionLocal() as db:
                                    repo = ProcessingTaskRepository(db)
                                    await repo.update_task(task_id, status="processing")
                                    await db.commit()
                            except: pass
                        
                        final_state = await agent.ainvoke(None, config=config)
                else:
                    if task_id:
                        try:
                            async with AsyncSessionLocal() as db:
                                repo = ProcessingTaskRepository(db)
                                await repo.update_task(task_id, status="processing")
                                await db.commit()
                        except: pass
                    final_state = await agent.ainvoke(initial_state, config=config)

            # Ensure final_state is a dict
            if not isinstance(final_state, dict):
                 logger.error(f"[{log_tag}] [{thread_id}] Agent returned non-dict state: {type(final_state)}")
                 return {}  # type: ignore

            # Check completion if a check is provided
            if completion_check and not completion_check(final_state):  # type: ignore
                logger.warning(f"[{log_tag}] [{thread_id}] ⚠️ Agent returned incomplete state (attempt {attempt})")
                if attempt < max_retries:
                    attempt += 1
                    await asyncio.sleep(0.5)
                    continue
                else:
                    raise RuntimeError(f"Agent {log_tag} failed to produce complete state after {max_retries} retries")
            
            duration = time.time() - start_time
            logger.info(f"[{log_tag}] [{thread_id}] Agent completed successfully in {duration:.2f}s")
            
            # Update task to completed
            if task_id:
                try:
                    async with AsyncSessionLocal() as db:
                        repo = ProcessingTaskRepository(db)
                        await repo.update_task(task_id, status="completed")
                        await db.commit()
                except: pass
                
            return final_state  # type: ignore

        except asyncio.CancelledError:
            logger.info(f"[{log_tag}] [{thread_id}] Agent execution cancelled.")
            if task_id:
                try:
                    async with AsyncSessionLocal() as db:
                        repo = ProcessingTaskRepository(db)
                        await repo.update_task(task_id, status="cancelled")
                        await db.commit()
                except: pass
            return {}  # type: ignore
        except Exception as e:
            logger.warning(f"[{log_tag}] [{thread_id}] ⚠️ Attempt {attempt} failed: {str(e)}")
            if attempt >= max_retries:
                logger.error(f"[{log_tag}] [{thread_id}] ❌ Agent failed after {max_retries} attempts.", exc_info=True)
                if task_id:
                    try:
                        async with AsyncSessionLocal() as db:
                            repo = ProcessingTaskRepository(db)
                            await repo.update_task(task_id, status="failed", error_message=str(e))
                            await db.commit()
                    except: pass
                if error_broadcaster:
                    await error_broadcaster(e)
                raise e
            attempt += 1
            await asyncio.sleep(0.5)
            
    return {} # Should not reach here

async def handle_active_task(
    thread_id: str,
    active_tasks: Dict[str, asyncio.Task],
    log_tag: str
) -> Optional[Dict[str, Any]]:
    """Checks if a task is already running and returns its result if it is."""
    if thread_id in active_tasks and not active_tasks[thread_id].done():
        logger.warning(f"[{log_tag}] [{thread_id}] Task already running, returning existing task.")
        result = await active_tasks[thread_id]
        return result if isinstance(result, dict) else {}
    return None

def manage_active_task(thread_id: str, active_tasks: Dict[str, asyncio.Task]):
    """Decorator-like context manager for active tasks would be nice, but simple assignment is fine."""
    task = asyncio.current_task()
    active_tasks[thread_id] = task
    return task

async def cancel_agent_task(
    thread_id: str,
    active_tasks: Dict[str, asyncio.Task],
    log_tag: str
) -> bool:
    """
    Common logic to cancel a running agent task.
    Returns True if a task was found and cancelled, False otherwise.
    """
    if thread_id in active_tasks:
        task = active_tasks[thread_id]
        if not task.done():
            logger.info(f"[{log_tag}] [{thread_id}] Cancelling active agent task.")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Double check if it's still in the dict (might have been removed by 'finally' block)
        if active_tasks.get(thread_id) == task:
            del active_tasks[thread_id]
        return True
    return False
