import json
import logging

from langchain_core.runnables import RunnableConfig

from ....agents.jd_processor.state import JDState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....database import AsyncSessionLocal
from ....repositories.job_repository import JobRepository
from ....services.embedding import EmbeddingService

logger = logging.getLogger(__name__)

embedding_service = EmbeddingService()

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
        # 1. Generate legacy embedding for the job description
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Generating legacy embedding for JD...")
        prepared_text = json.dumps(structured_data_dict, indent=2)
        legacy_embedding = await embedding_service.generate_embedding(prepared_text)
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Legacy embedding generated successfully.")

        # 2. Generate chunked embeddings for full text
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Generating chunked embeddings for full text...")
        full_text = state.get("raw_text", "")
        chunks = embedding_service.chunk_text(full_text)
        chunk_embeddings = await embedding_service.generate_embeddings(chunks)
        
        # NOTE: We ONLY include chunks here because 'legacy' is handled by update_job/create_job methods
        embeddings_to_save = []
        for i, (chunk, vector) in enumerate(zip(chunks, chunk_embeddings)):
            embeddings_to_save.append({
                "type": "chunk",
                "vector": vector,
                "metadata": {"index": i, "content": chunk}
            })
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] {len(chunks)} chunks generated and embedded.")

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
                        # Pass one for legacy backward compatibility if repo still needs it
                        embedding=legacy_embedding,
                        markdown_content=markdown_content,
                        org_id=state.get("org_id"),
                        raw_text=state.get("raw_text")
                    )
                else:
                    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Creating new job with ID {job_id}.")
                    # Use the provided job_id for creation
                    await repo.create_job_with_id(
                        job_id=job_id,
                        raw_text=state.get("raw_text"),
                        title=job_title,
                        structured_data=structured_data_dict,
                        embedding=legacy_embedding,
                        markdown_content=markdown_content,
                        org_id=state.get("org_id")
                    )
                
                # Store all new embeddings
                # Note: update_job might have replaced the legacy one, but we also want the chunks
                # For now, let's explicitly add them via the new method.
                # We should probably clear non-legacy ones if updating.
                from sqlalchemy import delete
                from src.models.db_models import Embedding
                await db.execute(
                    delete(Embedding).where(Embedding.job_id == job_id, Embedding.embedding_type != "legacy")
                )
                await repo.add_embeddings(job_id=job_id, embeddings=embeddings_to_save)
            else:
                logger.error(f"[JD_PROCESSOR] [{clean_id_str}] No job_id provided to update/create.")
            
            await db.commit()
            
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Job description finalized with ID: {job_id}")
        
    except Exception as e:
        logger.error(f"[JD_PROCESSOR] [{clean_id_str}] Validate and Save Node failed during finalization: {str(e)}", exc_info=True)
        raise e

    return state
