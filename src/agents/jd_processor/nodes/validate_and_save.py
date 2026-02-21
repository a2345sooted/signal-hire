import logging

from langchain_core.runnables import RunnableConfig

from ....agents.jd_processor.state import JDState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....database import AsyncSessionLocal
from ....repositories.job_repository import JobRepository
from ....services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

embedding_service = EmbeddingService()

def prepare_job_text_for_embedding(structured_data: dict) -> str:
    """
    Convert structured job description data into a single text representation
    optimized for semantic search and similarity matching.
    """
    parts = []
    
    if company := structured_data.get("company"):
        parts.append(f"Company: {company}")
    
    if title := structured_data.get("title"):
        parts.append(f"Title: {title}")
    
    if requirements := structured_data.get("requirements"):
        parts.append("Requirements:")
        for key, value in requirements.items():
            parts.append(f"{key}: {value}")
    
    if skills := structured_data.get("skills", []):
        parts.append(f"Skills: {', '.join(skills)}")
        
    return "\n".join(parts)

async def validate_and_save_node(state: JDState, config: RunnableConfig = None):
    """
    This node acts as a synchronization point for the parallel tracks.
    It also generates embeddings and broadcasts the final status.
    """
    thread_id_str = get_thread_id(state, config)
    
    # If it's the thread_id, it might have a prefix (e.g., jd_)
    clean_id_str = strip_id_prefix(thread_id_str)

    # Validate both parallel tracks completed successfully
    structured_data_dict = state.get("structured_data")
    markdown_content = state.get("markdown")
    job_id = state.get("job_id")

    if not structured_data_dict:
        raise RuntimeError(
            f"Structured data node failed to produce structured_data. "
            f"State keys present: {list(state.keys())}"
        )
    if not markdown_content:
        raise RuntimeError(
            f"Markdown generator node failed to produce markdown. "
            f"State keys present: {list(state.keys())}"
        )

    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Validate and Save Node - Parallel tracks synchronized and validated.")

    job_title = structured_data_dict.get("job_title") or structured_data_dict.get("title")

    try:
        from ....api.ws.manager import manager
        import json
        await manager.broadcast_to_job(
            json.dumps({"status": "Processing job description", "message": "Processing job description"}),
            str(job_id)
        )
        
        # Generate real embedding for the job description
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Generating embedding for JD...")
        prepared_text = prepare_job_text_for_embedding(structured_data_dict)
        embedding = await embedding_service.generate_embedding(prepared_text)
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Embedding generated successfully.")

        async with AsyncSessionLocal() as db:
            repo = JobRepository(db)
            
            if job_id:
                # Check if job already exists (it shouldn't based on new logic, but for robustness)
                existing_job = await repo.get_job_by_id(job_id)
                if existing_job:
                    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Updating existing job {job_id}.")
                    await repo.update_job(
                        job_id=job_id,
                        title=job_title,
                        structured_data=structured_data_dict,
                        embedding=embedding,
                        markdown_content=markdown_content,
                        org_id=state.get("org_id")
                    )
                else:
                    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Creating new job with ID {job_id}.")
                    # Use the provided job_id for creation
                    await repo.create_job_with_id(
                        job_id=job_id,
                        raw_text=state.get("raw_text"),
                        title=job_title,
                        structured_data=structured_data_dict,
                        embedding=embedding,
                        markdown_content=markdown_content,
                        org_id=state.get("org_id")
                    )
            else:
                logger.error(f"[JD_PROCESSOR] [{clean_id_str}] No job_id provided to update/create.")
            
            await db.commit()
            
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Job description finalized with ID: {job_id}")
        
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Broadcasting success message to job_id: {clean_id_str}")
        await manager.broadcast_to_job(
            json.dumps({
                "status": "Job description processed successfully!", 
                "message": "Job description processed successfully!",
                "completed": True,
                "job_id": str(job_id)
            }),
            str(job_id)
        )
        
    except Exception as e:
        logger.error(f"[JD_PROCESSOR] [{clean_id_str}] Validate and Save Node failed during finalization: {str(e)}", exc_info=True)
        raise e

    return state
