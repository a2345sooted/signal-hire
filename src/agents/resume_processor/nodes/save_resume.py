import logging

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

    # Generate embedding
    try:
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Generating embedding for resume...")
        prepared_text = embedding_service.prepare_resume_text_for_embedding(structured_data)
        embedding = await embedding_service.generate_embedding(prepared_text)
        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Embedding generated successfully.")
    except Exception as e:
        logger.error(f"[RESUME_PROCESSOR] [{clean_id_str}] Failed to generate embedding: {str(e)}")
        raise RuntimeError(f"Embedding generation is required for resume storage: {str(e)}") from e
    
    try:
        async with AsyncSessionLocal() as db:
            from ....repositories.candidate_repository import CandidateRepository
            candidate_repo = CandidateRepository(db)
            repo = ResumeRepository(db)
            
            # 1. Handle Candidate
            candidate_name = structured_data.get("contact", {}).get("name", "Unknown Candidate")
            candidate_email = structured_data.get("contact", {}).get("email", "unknown@unknown.com")
            
            # Map new fields from structured_data
            phone = structured_data.get("contact", {}).get("phone")
            location = structured_data.get("contact", {}).get("location")
            linkedin_url = structured_data.get("contact", {}).get("linkedin")
            citizenship = structured_data.get("citizenship")
            engagement_types = structured_data.get("engagement_types")
            work_preference = structured_data.get("work_preference")
            open_to_relocation = structured_data.get("open_to_relocation")

            candidate_id = await candidate_repo.get_or_create_candidate_by_name(
                candidate_name, 
                email=candidate_email,
                org_id=state.get("org_id")
            )
            
            # Update candidate with full info extracted from resume
            await candidate_repo.update_candidate(
                candidate_id=candidate_id,
                phone=phone,
                location=location,
                linkedin_url=linkedin_url,
                citizenship=citizenship,
                engagement_types=engagement_types,
                work_preference=work_preference,
                open_to_relocation=open_to_relocation
            )
            
            # 2. Handle Resume
            existing_resume_id = state.get("resume_id")
            
            if existing_resume_id:
                logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Updating existing resume ID: {existing_resume_id}")
                await repo.update_resume(
                    resume_id=existing_resume_id,
                    raw_text=raw_text,
                    structured_data=structured_data,
                    embedding=embedding,
                    storage_key=storage_key,
                    job_id=state.get("job_id"),
                    candidate_id=candidate_id
                )
                resume_id = existing_resume_id
            else:
                # Ensure filename is unique
                unique_filename = await repo.get_unique_filename(original_filename)
                if unique_filename != original_filename:
                    logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Renamed resume from {original_filename} to {unique_filename} to avoid collision.")

                resume_id = await repo.create_resume(
                    original_filename=unique_filename,
                    raw_text=raw_text,
                    structured_data=structured_data,
                    embedding=embedding,
                    storage_key=storage_key,
                    job_id=state.get("job_id"),
                    candidate_id=candidate_id
                )
            
            await db.commit()
            
        # 1. Trigger the Analyzer Agent
        job_id = state.get("job_id")
        if job_id:
            from ....agents.analyzer.run import run_analyzer_agent
            from ....repositories.job_repository import JobRepository
            
            async with AsyncSessionLocal() as db:
                jd_repo = JobRepository(db)
                job_data = await jd_repo.get_job_by_id(job_id)
                
            if job_data:
                # We run it in the background as a separate task
                import asyncio
                logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Triggering Analyzer Agent for job_id: {job_id}, candidate_id: {candidate_id}")
                asyncio.create_task(
                    run_analyzer_agent(
                        job_id=job_id,
                        candidate_id=candidate_id,
                        job_data=job_data,
                        resume_data={
                            "raw_text": raw_text,
                            "structured_data": structured_data
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
