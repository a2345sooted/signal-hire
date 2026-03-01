import json
import logging
import uuid

from langchain_core.runnables import RunnableConfig

from ....agents.resume_processor.state import ResumeState
from ....constants import NO_THREAD_ID
from ....database import AsyncSessionLocal
from ....repositories.resume_repository import ResumeRepository
from ....services.embedding import EmbeddingService
from ....services.pdf import PDFGenerator
from ....services.storage import storage_service

logger = logging.getLogger(__name__)

embedding_service = EmbeddingService()
pdf_generator = PDFGenerator()

from ....agents.utils import strip_id_prefix, get_thread_id

async def save_resume_node(state: ResumeState, config: RunnableConfig = None):
    """
    Saves the processed resume and its structured data to the database.
    If the uploaded file is a .docx, it also generates and stores a PDF version.
    """
    thread_id_str = get_thread_id(state, config)
    
    # If it's the thread_id, it might have a prefix (e.g., resume_)
    clean_id_str = strip_id_prefix(thread_id_str)

    logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Save Resume Node started.")
    
    if thread_id_str != NO_THREAD_ID:
        pass

    raw_text = state.get("raw_text")
    structured_data = state.get("structured_data")
    file_key = state.get("file_key")
    
    if not structured_data:
        raise RuntimeError(f"[RESUME_PROCESSOR] [{clean_id_str}] Missing structured_data for saving")

    # Handle PDF generation for DOCX uploads
    original_filename = state.get("metadata", {}).get("original_filename", "resume.pdf")
    storage_key = file_key
    
    if original_filename.lower().endswith(".docx"):
        try:
            logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] DOCX detected. Generating PDF version from structured data...")
            pdf_bytes = pdf_generator.generate_pdf(structured_data)
            pdf_filename = original_filename.rsplit(".", 1)[0] + ".pdf"
            # Store in the same directory as the original file
            dir_id = str(state.get("resume_id"))
            storage_key = await storage_service.upload_file_data(
                pdf_bytes, 
                pdf_filename, 
                content_type="application/pdf",
                dir_id=dir_id
            )
            logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] PDF version generated and stored: {storage_key}")
        except Exception as e:
            logger.error(f"[RESUME_PROCESSOR] [{clean_id_str}] Failed to generate/store PDF for DOCX: {str(e)}")

    # Validate required fields
    contact = structured_data.get("contact", {})
    if not contact.get("name") and not contact.get("email"):
         logger.warning(f"[RESUME_PROCESSOR] [{clean_id_str}] Resume parser produced no name or email - possible parsing issue.")

    # Generate embeddings
    try:
        # 1. Generate legacy embedding for the resume summary
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Generating legacy embedding for resume summary...")
        prepared_text = json.dumps(structured_data, indent=2)
        legacy_embedding = await embedding_service.generate_embedding(prepared_text)
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Legacy embedding generated successfully.")

        # 2. Generate chunked embeddings for full text
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Generating chunked embeddings for full resume text...")
        full_text = raw_text or ""
        chunks = embedding_service.chunk_text(full_text)
        chunk_embeddings = await embedding_service.generate_embeddings(chunks)
        
        # NOTE: We ONLY include chunks here because 'legacy' is handled by update_resume/create_resume methods
        embeddings_to_save = []
        for i, (chunk, vector) in enumerate(zip(chunks, chunk_embeddings)):
            embeddings_to_save.append({
                "type": "chunk",
                "vector": vector,
                "metadata": {"index": i, "content": chunk}
            })
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] {len(chunks)} chunks generated and embedded.")
    except Exception as e:
        logger.error(f"[RESUME_PROCESSOR] [{clean_id_str}] Failed to generate embeddings: {str(e)}")
        raise RuntimeError(f"Embedding generation is required for resume storage: {str(e)}") from e
    
    try:
        async with AsyncSessionLocal() as db:
            from ....repositories.candidate_repository import CandidateRepository
            candidate_repo = CandidateRepository(db)
            repo = ResumeRepository(db)
            
            # 1. Handle Candidate
            candidate_id = state.get("candidate_id")
            
            # Map new fields from structured_data
            candidate_name = structured_data.get("contact", {}).get("name")
            candidate_email = structured_data.get("contact", {}).get("email")
            phone = structured_data.get("contact", {}).get("phone")
            location = structured_data.get("contact", {}).get("location")
            linkedin_url = structured_data.get("contact", {}).get("linkedin")
            citizenship = structured_data.get("citizenship")
            engagement_types = structured_data.get("engagement_types")
            work_preference = structured_data.get("work_preference")
            open_to_relocation = structured_data.get("open_to_relocation")

            if not candidate_id:
                logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] No candidate_id in state. Using get_or_create_candidate_by_name as fallback.")
                candidate_id = await candidate_repo.get_or_create_candidate_by_name(
                    candidate_name or "Unknown Candidate", 
                    email=candidate_email or "unknown@unknown.com",
                    org_id=state.get("org_id")
                )
            
            # Update candidate with full info extracted from resume
            # We ONLY update fields if they are currently null or empty in the database.
            candidate_to_update = await candidate_repo.get_candidate_by_id(candidate_id)
            update_kwargs = {}
            if candidate_to_update:
                # Basic info
                if not candidate_to_update.get("name") and candidate_name:
                    update_kwargs["name"] = candidate_name
                if not candidate_to_update.get("email") and candidate_email:
                    update_kwargs["email"] = candidate_email
                if not candidate_to_update.get("phone") and phone:
                    update_kwargs["phone"] = phone
                if not candidate_to_update.get("location") and location:
                    update_kwargs["location"] = location
                if not candidate_to_update.get("linkedin_url") and linkedin_url:
                    update_kwargs["linkedin_url"] = linkedin_url
                
                # New fields
                if not candidate_to_update.get("citizenship") and citizenship:
                    update_kwargs["citizenship"] = citizenship
                if not candidate_to_update.get("engagement_types") and engagement_types:
                    update_kwargs["engagement_types"] = engagement_types
                if not candidate_to_update.get("work_preference") and work_preference:
                    update_kwargs["work_preference"] = work_preference
                
                # Note: open_to_relocation is a boolean, so we only update if it's currently False (default) and extracted is True
                if not candidate_to_update.get("open_to_relocation") and open_to_relocation is True:
                    update_kwargs["open_to_relocation"] = open_to_relocation

            if update_kwargs:
                await candidate_repo.update_candidate(
                    candidate_id=candidate_id,
                    **update_kwargs
                )
            
            # 2. Handle Resume
            existing_resume_id = state.get("resume_id")
            
            if existing_resume_id:
                logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Updating existing resume ID: {existing_resume_id}")
                await repo.update_resume(
                    resume_id=existing_resume_id,
                    raw_text=raw_text,
                    structured_data=structured_data,
                    embedding=legacy_embedding,
                    storage_key=storage_key,
                    job_id=state.get("job_id"),
                    candidate_id=candidate_id
                )
                resume_id = existing_resume_id
            else:
                # ENFORCE SINGLE ORIGINAL RESUME CONSTRAINT
                # Check if this candidate already has an original resume
                existing_original = await repo.get_original_resume_by_candidate_id(candidate_id)
                
                if existing_original:
                    logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Candidate {candidate_id} already has a resume {existing_original.id}. Overwriting.")
                    
                    # Delete old storage if different
                    if existing_original.storage_key and existing_original.storage_key != storage_key:
                        try:
                            await storage_service.delete_file(existing_original.storage_key)
                        except: pass
                    
                    # Update existing record instead of creating new one
                    await repo.update_resume(
                        resume_id=existing_original.id,
                        raw_text=raw_text,
                        structured_data=structured_data,
                        embedding=legacy_embedding,
                        storage_key=storage_key, # Use the new storage key
                        job_id=state.get("job_id"),
                        candidate_id=candidate_id
                    )
                    resume_id = existing_original.id
                    
                    # If the thread was started with a new resume_id, we might have an orphan skeleton
                    # created in the API. Let's check.
                    if state.get("resume_id") and state.get("resume_id") != resume_id:
                         # This shouldn't happen if existing_resume_id was set, but just in case
                         pass
                else:
                    # Ensure filename is unique
                    unique_filename = await repo.get_unique_filename(original_filename)
                    if unique_filename != original_filename:
                        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Renamed resume from {original_filename} to {unique_filename} to avoid collision.")

                    resume_id = await repo.create_resume(
                        original_filename=unique_filename,
                        raw_text=raw_text,
                        structured_data=structured_data,
                        embedding=legacy_embedding,
                        storage_key=storage_key,
                        job_id=state.get("job_id"),
                        candidate_id=candidate_id
                    )
            
            # 3. Handle additional embeddings
            from sqlalchemy import delete
            from src.models.db_models import Embedding, ProcessingTask
            await db.execute(
                delete(Embedding).where(Embedding.resume_id == resume_id, Embedding.embedding_type != "legacy")
            )
            await repo.add_embeddings(resume_id=resume_id, candidate_id=candidate_id, embeddings=embeddings_to_save)
            
            # Delete the resume task as it's finished saving and parsing
            await db.execute(
                delete(ProcessingTask).where(ProcessingTask.id == resume_id)
            )
            
            # Update any existing attachments that don't have a resume_id
            from src.models.db_models import JobAttachment
            from sqlalchemy import update
            await db.execute(
                update(JobAttachment)
                .where(JobAttachment.candidate_id == candidate_id)
                .where(JobAttachment.resume_id == None)
                .values(resume_id=resume_id)
            )
            
            await db.commit()
            
        # 1. Trigger the Analyzer Agent for the specific job if provided
        job_id = state.get("job_id")
        from ....agents.analyzer.run import run_analyzer_agent
        from ....repositories.job_repository import JobRepository
        from ....repositories.analysis_repository import AnalysisRepository
        from ....repositories.processing_task_repository import ProcessingTaskRepository
        import asyncio
        import hashlib

        async with AsyncSessionLocal() as db:
            jd_repo = JobRepository(db)
            analysis_repo = AnalysisRepository(db)
            task_repo = ProcessingTaskRepository(db)
            
            # Identify all jobs this candidate is attached to
            attached_jobs = await jd_repo.get_attached_jobs(candidate_id)
            
            # Also include the job_id from state if it's not already in attached_jobs
            # (though normally it should be attached by now)
            job_ids_to_process = {uuid.UUID(job["id"]) for job in attached_jobs}
            if job_id:
                job_ids_to_process.add(job_id)
            
            # Map job_id to job_data for processing
            jobs_to_process = {uuid.UUID(job["id"]): job for job in attached_jobs}
            if job_id and job_id not in jobs_to_process:
                job_data = await jd_repo.get_job_by_id(job_id)
                if job_data:
                    jobs_to_process[job_id] = job_data

            for jid, job in jobs_to_process.items():
                logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Processing re-analysis for job {jid}")
                
                # A. Remove any existing optimized resumes for this job and candidate
                # Refresh resumes list to get latest state
                all_resumes_for_cleanup = await repo.get_resumes_by_candidate_id(candidate_id)
                for r in all_resumes_for_cleanup:
                    if r.is_optimized and str(r.job_id) == str(jid):
                        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Removing optimized resume {r.id} for job {jid}")
                        if r.storage_key:
                            try:
                                await storage_service.delete_file(r.storage_key)
                            except Exception as e:
                                logger.warning(f"[RESUME_PROCESSOR] [{clean_id_str}] Failed to delete optimized resume file {r.storage_key}: {e}")
                        
                        await repo.delete_resume(r.id)
                
                await db.flush() # Ensure deletes are flushed before re-analysis trigger

                # B. Trigger re-analysis
                raw_jd = job.get("raw_text", "")
                details = job.get("details", {})
                
                jd_hash = hashlib.sha256(raw_jd.encode()).hexdigest() if raw_jd else None
                details_hash = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest() if details else None

                existing = await analysis_repo.get_analysis_for_candidate_job_resume(
                    candidate_id=candidate_id,
                    job_id=jid,
                    resume_id=resume_id
                )
                
                # We always re-analyze when resume changes, but we still update hashes
                logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Triggering Analyzer Agent for job_id: {jid}, candidate_id: {candidate_id}")
                
                skeleton_content = {"status": "processing", "message": "Resume updated. Analysis is being re-generated..."}
                if existing:
                    await analysis_repo.update_analysis(
                        analysis_id=uuid.UUID(existing["id"]),
                        content=skeleton_content,
                        jd_hash=jd_hash,
                        details_hash=details_hash,
                        resume_id=resume_id
                    )
                    analysis_id = uuid.UUID(existing["id"])
                else:
                    analysis_id = await analysis_repo.create_analysis(
                        candidate_id=candidate_id,
                        job_id=jid,
                        content=skeleton_content,
                        resume_id=resume_id,
                        jd_hash=jd_hash,
                        details_hash=details_hash
                    )
                
                # Pre-register the task in the database
                await task_repo.create_task(
                    task_id=analysis_id,
                    task_type="analysis",
                    job_id=jid,
                    candidate_id=candidate_id,
                    resume_id=resume_id,
                    status="starting"
                )
                await db.commit() # Commit each to make it visible
                
                asyncio.create_task(
                    run_analyzer_agent(
                        job_id=jid,
                        candidate_id=candidate_id,
                        job_data=job,
                        resume_data={
                            "raw_text": raw_text,
                            "structured_data": structured_data,
                            "resume_id": str(resume_id)
                        },
                        personal_info_mismatch_question=state.get("personal_info_mismatch_question"),
                        org_id=state.get("org_id")
                    )
                )

        if thread_id_str != NO_THREAD_ID:
            pass
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Resume saved with ID: {resume_id}, Candidate ID: {candidate_id}")
        return {"resume_id": resume_id, "candidate_id": candidate_id}
    except Exception as e:
        logger.error(f"[RESUME_PROCESSOR] [{clean_id_str}] Save Resume Node failed: {str(e)}", exc_info=True)
        raise e
