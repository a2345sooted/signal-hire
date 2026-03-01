import logging
import uuid
import json
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.database import get_db, AsyncSessionLocal
from src.repositories.job_repository import JobRepository
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.models.db_models import Resume
from src.ai_model_factory import get_model, MODEL_5_2

logger = logging.getLogger(__name__)

async def generate_diff_task(resume_id: uuid.UUID):
    """
    Background task to generate an LLM-powered diff and update the resume record.
    """
    logger.info(f"Starting background LLM diff generation for resume: {resume_id}")
    
    try:
        async with AsyncSessionLocal() as db:
            repo = ResumeRepository(db)
            
            # Fetch the optimized resume
            result = await db.execute(select(Resume).where(Resume.id == resume_id))
            optimized_resume = result.scalar_one_or_none()
            
            if not optimized_resume:
                logger.error(f"Resume {resume_id} not found for diff update")
                return

            if not optimized_resume.parent_id:
                logger.warning(f"Resume {resume_id} has no parent_id. Cannot generate diff.")
                return

            # Fetch the parent (original) resume
            parent_result = await db.execute(select(Resume).where(Resume.id == optimized_resume.parent_id))
            parent_resume = parent_result.scalar_one_or_none()
            
            if not parent_resume:
                logger.error(f"Parent resume {optimized_resume.parent_id} not found for diff generation")
                return

            # Get structured data for both
            original_structured = parent_resume.structured_data
            optimized_structured = optimized_resume.structured_data
            
            # Use LLM to generate the diff
            llm = get_model(model_name=MODEL_5_2)
            
            prompt = f"""You are an expert Resume Editor. Your task is to generate a highly readable, professionally formatted Markdown document that explains PRECISELY what was changed during the resume optimization process.

CRITICAL: Do NOT use placeholder names like "Robert Schupp", "Tech Solutions Inc.", or generic "placeholder" text in your output. Use ONLY the data provided below.

ORIGINAL RESUME DATA (JSON):
{json.dumps(original_structured, indent=2)}

OPTIMIZED RESUME DATA (JSON):
{json.dumps(optimized_structured, indent=2)}

INSTRUCTIONS:
1.  **Format**: Use clean, well-structured, and spacious Markdown. 
2.  **Summary**: Start with a high-level summary of the overall optimization strategy used for this candidate. Wrap this summary in a blockquote or a separate section to distinguish it.
3.  **Section-by-Section Comparison**: 
    - Use clear, level 3 headers for each resume section (e.g., ### Professional Summary).
    - Use a horizontal rule (`---`) between major sections to improve scanability.
    - For each section, use a detailed bulleted list to describe specific changes.
    - Use bold text for labels and to highlight key improvements or added keywords.
    - Follow this EXACT format for each change:
      * **Changed from**: "[Original text segment...]" 
      * **Changed to**: "[Optimized text segment...]"
      * **Reason**: [Brief explanation of why this change improves ATS matching or role alignment].
    - Ensure there is an empty line between each bullet point to prevent the document from feeling cluttered.
4.  **Additions/Deletions**: Clearly label any entirely new sections or skills added (e.g., **[ADDED]**), and any information removed.
5.  **Spacing**: Use multiple line breaks between headers and lists. The output must be super easy to scan and read on a screen.
6.  **Style**: Professional, objective, and impact-oriented.

Generate the "Resume Optimization Diff" in Markdown format.
"""
            
            logger.info(f"Invoking LLM for diff generation for resume {resume_id}. Prompt length: {len(prompt)}")
            response = await llm.ainvoke(prompt)
            diff_markdown = response.content if hasattr(response, "content") else str(response)

            # Update the resume record
            current_diff = (optimized_resume.diff or {}).copy()
            current_diff["markdown"] = diff_markdown
            
            logger.info(f"Writing LLM-generated diff to resume {resume_id}. Diff length: {len(diff_markdown)}")
            if "placeholder" in diff_markdown.lower() or "robert schupp" in diff_markdown.lower():
                logger.warning(f"LLM generated a diff that contains placeholder keywords for resume {resume_id}!")
                logger.debug(f"LLM response snippet: {diff_markdown[:500]}...")

            # We must use the repository to update
            await repo.update_resume(resume_id, diff=current_diff)
            await db.commit()
            logger.info(f"Successfully updated LLM-generated diff for resume {resume_id}")
                
    except Exception as e:
        logger.error(f"Error in generate_diff_task for resume {resume_id}: {str(e)}", exc_info=True)

async def generate_resume_diff(
    request: Request,
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    x_org_slug: Annotated[str, Header(alias="X-Org-Slug")],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Kicks off an async process to generate a diff for the latest optimized resume.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not belong to this organization")

    job_repo = JobRepository(db)
    job = await job_repo.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if str(job.get("org_id")) != str(org.id):
        raise HTTPException(status_code=403, detail="Job does not belong to this organization")

    repo = ResumeRepository(db)
    all_resumes = await repo.get_resumes_by_candidate_id(candidate_id)
    
    optimized_resume = None
    if all_resumes:
        matching = [
            r for r in all_resumes 
            if getattr(r, "is_optimized", False) and str(getattr(r, "job_id", "")) == str(job_id)
        ]
        if matching:
            # Sort by created_at descending to get the LATEST optimized resume
            from datetime import datetime, timezone
            matching.sort(key=lambda r: r.created_at if r.created_at else datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            optimized_resume = matching[0] # Latest one

    if not optimized_resume:
        raise HTTPException(status_code=404, detail="No optimized resume found for this job and candidate")

    background_tasks.add_task(generate_diff_task, optimized_resume.id)

    return {
        "success": True,
        "message": "Diff generation started in the background."
    }
