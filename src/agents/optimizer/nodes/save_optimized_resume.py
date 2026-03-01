import logging
import uuid
import json
from langchain_core.runnables import RunnableConfig
from ....agents.optimizer.state import OptimizerState
from ....database import AsyncSessionLocal
from ....repositories.resume_repository import ResumeRepository
from ....repositories.analysis_repository import AnalysisRepository
from ....repositories.processing_task_repository import ProcessingTaskRepository
from ....agents.analyzer.run import run_analyzer_agent
from ....agents.utils import strip_id_prefix, get_thread_id, generate_thread_id, get_task_id
from ....services.embedding import EmbeddingService
from ....services.pdf import PDFGenerator
from ....services.storage import storage_service

logger = logging.getLogger(__name__)
embedding_service = EmbeddingService()
pdf_generator = PDFGenerator()

async def save_optimized_resume_node(state: OptimizerState, config: RunnableConfig = None):
    """
    Saves the optimized resume to the database as a new record.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Save Optimized Resume Node started.")
    
    optimized_resume = state.get("optimized_resume")
    if not optimized_resume:
        raise RuntimeError(f"[OPTIMIZER_AGENT] [{clean_id_str}] Missing optimized_resume for saving.")

    candidate_id = state.get("candidate_id")
    job_id = state.get("job_id")
    org_id = state.get("org_id")
    parent_resume_id = state.get("resume_id")
    optimization_plan = state.get("optimization_plan")
    diff_markdown = state.get("diff_markdown")
    
    # Convert Pydantic model to dict
    structured_data = optimized_resume.model_dump()
    diff_data = (optimization_plan.model_dump() if optimization_plan else {}).copy()
    if diff_markdown:
        diff_data["markdown"] = diff_markdown
    
    logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Diff data to save: markdown length {len(diff_markdown) if diff_markdown else 0}")
    if diff_markdown and "placeholder" in diff_markdown.lower():
        logger.warning(f"[OPTIMIZER_AGENT] [{clean_id_str}] diff_markdown contains 'placeholder'!")

    # Generate embeddings for the new resume
    logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Generating embeddings for optimized resume...")
    prepared_text = json.dumps(structured_data, indent=2)
    legacy_embedding = await embedding_service.generate_embedding(prepared_text)
    
    # We might want to generate chunks too, but for optimized resumes, legacy might be enough for now.
    # Actually, let's stick to the standard: legacy + chunks.
    # We don't have 'raw_text' for the optimized resume yet, it's just structured.
    # We'll use the JSON representation as raw_text for now or generate a markdown version.
    # For now, let's just use JSON as raw_text.
    raw_text = prepared_text 
    
    chunks = embedding_service.chunk_text(raw_text)
    chunk_embeddings = await embedding_service.generate_embeddings(chunks)
    
    embeddings_to_save = []
    for i, (chunk, vector) in enumerate(zip(chunks, chunk_embeddings)):
        embeddings_to_save.append({
            "type": "chunk",
            "vector": vector,
            "metadata": {"index": i, "content": chunk}
        })

    try:
        async with AsyncSessionLocal() as db:
            repo = ResumeRepository(db)
            
            # Pre-generate a resume ID so we can use it in the storage key
            new_resume_id = uuid.uuid4()
            # Follow new convention for optimized resumes: candidates/:candidateId/resumes/optimized/:resumeId
            storage_key = f"candidates/{candidate_id}/resumes/optimized/{new_resume_id}"
            
            # Create a unique filename for the optimized resume
            original_resume_data = state.get("resume_data", {})
            original_filename = original_resume_data.get("filename") or "resume.pdf"
            base_name = original_filename.rsplit(".", 1)[0]
            ext = "pdf" # We'll eventually generate a PDF for it
            optimized_filename = f"{base_name}_optimized.{ext}"
            unique_filename = await repo.get_unique_filename(optimized_filename)
            
            # Generate PDF from structured data
            logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Generating PDF for optimized resume...")
            try:
                pdf_bytes = pdf_generator.generate_pdf(structured_data)
                # Upload PDF to storage
                await storage_service.upload_file_data_with_key(
                    file_data=pdf_bytes,
                    storage_key=storage_key,
                    content_type="application/pdf"
                )
                logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Optimized PDF uploaded to {storage_key}")
            except Exception as pdf_error:
                logger.error(f"[OPTIMIZER_AGENT] [{clean_id_str}] Failed to generate or upload PDF: {str(pdf_error)}")
                # We still continue saving the record even if PDF fails, 
                # though it's better if it succeeds.
            
            await repo.create_resume_with_id(
                resume_id=new_resume_id,
                original_filename=unique_filename,
                raw_text=raw_text,
                structured_data=structured_data,
                embedding=legacy_embedding,
                storage_key=storage_key,
                job_id=uuid.UUID(job_id),
                candidate_id=uuid.UUID(candidate_id),
                is_generated=True,
                is_optimized=True,
                parent_id=uuid.UUID(parent_resume_id) if parent_resume_id else None,
                diff=diff_data
            )
            
            # Add chunk embeddings
            from sqlalchemy import delete
            from src.models.db_models import Embedding
            await db.execute(
                delete(Embedding).where(Embedding.resume_id == new_resume_id, Embedding.embedding_type != "legacy")
            )
            await repo.add_embeddings(resume_id=new_resume_id, candidate_id=uuid.UUID(candidate_id), embeddings=embeddings_to_save)
            
            await db.commit()
            logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Optimized resume saved with ID: {new_resume_id} and storage_key: {storage_key}")

            # TRIGGER NEW ANALYSIS FOR THE OPTIMIZED RESUME
            try:
                # Pre-register the task in the database for UI tracking
                # We use a unique thread_id for the optimized analysis
                analysis_thread_id_id = f"{candidate_id}_opt"
                analysis_thread_id = generate_thread_id("analysis", uuid.UUID(job_id), analysis_thread_id_id)
                analysis_task_id = get_task_id(analysis_thread_id)

                # Fetch candidate notes/location for analysis context
                from ....repositories.candidate_repository import CandidateRepository
                candidate_repo = CandidateRepository(db)
                candidate_data = await candidate_repo.get_candidate_by_id(uuid.UUID(candidate_id))
                candidate_notes = candidate_data.get("notes", []) if candidate_data else []
                candidate_location = candidate_data.get("location") if candidate_data else None

                # Calculate hashes for JD and Details
                job_data = state.get("job_data", {})
                raw_jd = job_data.get("raw_text", "")
                details = job_data.get("details", {})
                import hashlib
                jd_hash = hashlib.sha256(raw_jd.encode()).hexdigest() if raw_jd else None
                details_hash = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest() if details else None

                # Create processing task record
                task_repo = ProcessingTaskRepository(db)
                await task_repo.create_task(
                    task_id=analysis_task_id,
                    task_type="analysis",
                    job_id=uuid.UUID(job_id),
                    candidate_id=uuid.UUID(candidate_id),
                    resume_id=new_resume_id,
                    status="starting"
                )

                # Create initial analysis record
                analysis_repo = AnalysisRepository(db)
                skeleton_content = {"status": "processing", "message": "Analyzing optimized resume..."}
                await analysis_repo.create_analysis(
                    candidate_id=uuid.UUID(candidate_id),
                    job_id=uuid.UUID(job_id),
                    content=skeleton_content,
                    resume_id=new_resume_id,
                    jd_hash=jd_hash,
                    details_hash=details_hash
                )
                await db.commit()

                logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Triggering analysis for optimized resume {new_resume_id}")
                
                # Start the analyzer agent
                # Note: This is already running in a background context (via the optimizer's background task)
                import asyncio
                asyncio.create_task(run_analyzer_agent(
                    job_id=uuid.UUID(job_id),
                    candidate_id=uuid.UUID(candidate_id),
                    job_data=job_data,
                    resume_data={
                        "raw_text": raw_text,
                        "structured_data": structured_data,
                        "resume_id": str(new_resume_id)
                    },
                    candidate_notes=candidate_notes,
                    candidate_location=candidate_location,
                    thread_id_id=analysis_thread_id_id, # Use the same stable identifier
                    org_id=org_id
                ))
            except Exception as analysis_trigger_error:
                logger.error(f"[OPTIMIZER_AGENT] [{clean_id_str}] Failed to trigger analysis for optimized resume: {str(analysis_trigger_error)}")
            
            return {
                "new_resume_id": str(new_resume_id),
                "messages": state.get("messages", []) + [f"Optimized resume saved with ID: {new_resume_id}"]
            }
    except Exception as e:
        logger.error(f"[OPTIMIZER_AGENT] [{clean_id_str}] Save Optimized Resume Node failed: {str(e)}", exc_info=True)
        raise e
