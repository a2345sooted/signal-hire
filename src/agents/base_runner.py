import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, Protocol, TypeVar, Mapping

from .utils import get_checkpoint_config

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
    
    while attempt <= max_retries:
        try:
            if attempt > 1:
                logger.info(f"[{log_tag}] [{thread_id}] 🔄 Retrying agent (attempt {attempt}/{max_retries})")
                
                # Try to resume from checkpoint
                checkpoint_config = get_checkpoint_config(thread_id)
                state = await agent.aget_state(checkpoint_config)
                
                if state and state.values:
                    # If we have a completion check and it passes for the checkpoint state, return it
                    if completion_check and completion_check(state.values):  # type: ignore
                        logger.info(f"[{log_tag}] [{thread_id}] Found completed state in checkpoint.")
                        return state.values  # type: ignore
                    
                    logger.info(f"[{log_tag}] [{thread_id}] Resuming from checkpoint...")
                    final_state = await agent.ainvoke(state.values, config=config)
                else:
                    logger.info(f"[{log_tag}] [{thread_id}] No checkpoint found, restarting.")
                    final_state = await agent.ainvoke(initial_state, config=config)
            else:
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
            return final_state  # type: ignore

        except asyncio.CancelledError:
            logger.info(f"[{log_tag}] [{thread_id}] Agent execution cancelled.")
            return {}  # type: ignore
        except Exception as e:
            logger.warning(f"[{log_tag}] [{thread_id}] ⚠️ Attempt {attempt} failed: {str(e)}")
            if attempt >= max_retries:
                logger.error(f"[{log_tag}] [{thread_id}] ❌ Agent failed after {max_retries} attempts.", exc_info=True)
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
