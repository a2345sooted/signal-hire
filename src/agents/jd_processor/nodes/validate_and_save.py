import json
import logging

from langchain_core.runnables import RunnableConfig

from ....agents.jd_processor.state import JDState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....database import AsyncSessionLocal
from ....constants import TASK_ANALYSIS
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
    details_dict = state.get("details")
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
    # Note: details_dict is optional for now, we don't raise error if it's missing, 
    # but we expect it since we added it to the graph.

    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Validate and Save Node - Parallel tracks synchronized and validated.")

    job_title = structured_data_dict.get("job_title") or structured_data_dict.get("title")

    try:
        # 1. Generate legacy embedding for the job description
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Generating legacy embedding for JD...")
        
        job_notes = []
        async with AsyncSessionLocal() as db:
            tmp_repo = JobRepository(db)
            if job_id:
                job_notes = await tmp_repo.get_job_notes(job_id)

        prepared_text = embedding_service.prepare_job_text_for_embedding(
            structured_data_dict, 
            job_data={
                "title": job_title,
                "location": state.get("location") or (details_dict.get("location") if details_dict else None),
                "work_arrangement": state.get("work_arrangement") or (details_dict.get("arrangement") if details_dict else None),
                "hybrid_days_per_week": state.get("hybrid_days_per_week") or (details_dict.get("hybrid_days_week") if details_dict else None),
                "pay_range_min": state.get("pay_range_min") or (details_dict.get("pay_range_min") if details_dict else None),
                "pay_range_max": state.get("pay_range_max") or (details_dict.get("pay_range_max") if details_dict else None),
                "pay_type": state.get("pay_type") or (details_dict.get("pay_type") if details_dict else None),
                "employment_type": state.get("employment_type") or (", ".join(details_dict.get("employment_type", [])) if details_dict else None),
                "offers_relocation": state.get("offers_relocation") or (details_dict.get("offers_relocation", False) if details_dict else False)
            },
            notes=job_notes
        )
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
                    
                    # Update job fields if they are currently null or blank in the database
                    update_kwargs = {
                        "job_id": job_id,
                        "structured_data": structured_data_dict,
                        "embedding": legacy_embedding,
                        "markdown_content": markdown_content,
                        "org_id": state.get("org_id"),
                        "raw_text": state.get("raw_text"),
                        "details": details_dict
                    }

                    # Only overwrite the job title if it is currently blank or null
                    if not existing_job.get("title") and job_title:
                        update_kwargs["title"] = job_title
                    
                    if details_dict:
                        # Map details to top-level fields if currently null
                        if not existing_job.get("location") and details_dict.get("location"):
                            update_kwargs["location"] = details_dict.get("location")
                        if not existing_job.get("work_arrangement") and details_dict.get("arrangement"):
                            update_kwargs["work_arrangement"] = details_dict.get("arrangement")
                        if existing_job.get("hybrid_days_per_week") is None and details_dict.get("hybrid_days_week") is not None:
                            update_kwargs["hybrid_days_per_week"] = details_dict.get("hybrid_days_week")
                        if existing_job.get("pay_range_min") is None and details_dict.get("pay_range_min") is not None:
                            update_kwargs["pay_range_min"] = details_dict.get("pay_range_min")
                        if existing_job.get("pay_range_max") is None and details_dict.get("pay_range_max") is not None:
                            update_kwargs["pay_range_max"] = details_dict.get("pay_range_max")
                        if not existing_job.get("pay_type") and details_dict.get("pay_type"):
                            update_kwargs["pay_type"] = details_dict.get("pay_type")
                        
                        # employment_type in JobDetailsSchema is a list, but top-level Job.employment_type is a string
                        # For consistency with candidate work preferences, let's take the first or comma-separated
                        extracted_emp_types = details_dict.get("employment_type", [])
                        if not existing_job.get("employment_type") and extracted_emp_types:
                             update_kwargs["employment_type"] = ", ".join(extracted_emp_types)
                        
                        # offers_relocation is a boolean with False as default. 
                        # We only update to True if it's currently False and extracted is True
                        if not existing_job.get("offers_relocation") and details_dict.get("offers_relocation") is True:
                            update_kwargs["offers_relocation"] = True

                    await repo.update_job(**update_kwargs)
                else:
                    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Creating new job with ID {job_id}.")
                    # Use the provided job_id for creation
                    # If we have details, we should also use them for the top-level fields
                    creation_kwargs = {
                        "job_id": job_id,
                        "raw_text": state.get("raw_text"),
                        "title": job_title,
                        "structured_data": structured_data_dict,
                        "embedding": legacy_embedding,
                        "markdown_content": markdown_content,
                        "org_id": state.get("org_id"),
                        "details": details_dict
                    }
                    
                    if details_dict:
                        creation_kwargs.update({
                            "location": details_dict.get("location"),
                            "work_arrangement": details_dict.get("arrangement"),
                            "hybrid_days_per_week": details_dict.get("hybrid_days_week"),
                            "pay_range_min": details_dict.get("pay_range_min"),
                            "pay_range_max": details_dict.get("pay_range_max"),
                            "pay_type": details_dict.get("pay_type"),
                            "employment_type": ", ".join(details_dict.get("employment_type", [])),
                            "offers_relocation": details_dict.get("offers_relocation", False)
                        })

                    await repo.create_job_with_id(**creation_kwargs)
                
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
            
            # 3. Trigger re-analysis for all attached candidates
            from ....agents.analyzer.run import run_analyzer_agent
            from ....repositories.candidate_repository import CandidateRepository
            from ....repositories.analysis_repository import AnalysisRepository
            import asyncio
            import uuid
            import hashlib

            candidate_repo = CandidateRepository(db)
            analysis_repo = AnalysisRepository(db)
            attached_candidates = await repo.get_attached_candidates(job_id)
            
            job_data_for_analysis = await repo.get_job_by_id(job_id)

            raw_jd = state.get("raw_text", "")
            jd_hash = hashlib.sha256(raw_jd.encode()).hexdigest() if raw_jd else None
            details_hash = hashlib.sha256(json.dumps(details_dict, sort_keys=True).encode()).hexdigest() if details_dict else None

            for candidate in attached_candidates:
                candidate_id = uuid.UUID(candidate["id"])
                current_resume = await candidate_repo.get_latest_resume(candidate_id)
                
                if current_resume:
                    resume_id = uuid.UUID(current_resume["id"])
                    
                    # Check if re-analysis is actually needed
                    existing = await analysis_repo.get_analysis_for_candidate_job_resume(
                        candidate_id=candidate_id,
                        job_id=job_id,
                        resume_id=resume_id
                    )
                    
                    needs_analysis = True
                    if existing:
                        # Check if hashes match
                        if existing.get("jd_hash") == jd_hash and existing.get("details_hash") == details_hash:
                            content = existing.get("content", {})
                            if content.get("status") != "processing":
                                needs_analysis = False
                                logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Analysis already valid for candidate {candidate_id}. Skipping.")

                    if needs_analysis:
                        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Triggering re-analysis for candidate {candidate_id} on job {job_id}")
                        
                        # Create/Update skeleton analysis record
                        skeleton_content = {"status": "processing", "message": "Job description updated. Re-analyzing..."}
                        
                        if existing:
                            await analysis_repo.update_analysis(
                                analysis_id=uuid.UUID(existing["id"]),
                                content=skeleton_content,
                                jd_hash=jd_hash,
                                details_hash=details_hash
                            )
                            analysis_id_re = uuid.UUID(existing["id"])
                        else:
                            analysis_id_re = await analysis_repo.create_analysis(
                                candidate_id=candidate_id,
                                job_id=job_id,
                                content=skeleton_content,
                                resume_id=resume_id,
                                jd_hash=jd_hash,
                                details_hash=details_hash
                            )
                        
                        # Pre-register the task in the database
                        from ....repositories.processing_task_repository import ProcessingTaskRepository
                        task_repo = ProcessingTaskRepository(db)
                        await task_repo.create_task(
                            task_id=analysis_id_re,
                            task_type=TASK_ANALYSIS,
                            job_id=job_id,
                            candidate_id=candidate_id,
                            resume_id=resume_id,
                            status="starting"
                        )
                        await db.commit()
                        
                        asyncio.create_task(
                            run_analyzer_agent(
                                job_id=job_id,
                                candidate_id=candidate_id,
                                job_data=job_data_for_analysis,
                                resume_data={
                                    "raw_text": current_resume["raw_text"],
                                    "structured_data": current_resume["structured_data"],
                                    "resume_id": str(resume_id)
                                },
                                org_id=state.get("org_id")
                            )
                        )
                else:
                    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Skipping analysis for candidate {candidate_id} - no current resume.")

        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Job description finalized with ID: {job_id}")
        
    except Exception as e:
        logger.error(f"[JD_PROCESSOR] [{clean_id_str}] Validate and Save Node failed during finalization: {str(e)}", exc_info=True)
        raise e

    return state
