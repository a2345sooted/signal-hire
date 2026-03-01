import logging
import uuid
import json
from typing import Annotated
from fastapi import Depends, Request, HTTPException, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.database import get_db, AsyncSessionLocal
from src.repositories.organization_repository import OrganizationRepository
from src.repositories.resume_repository import ResumeRepository
from src.models.db_models import Resume
from src.ai_model_factory import get_model, MODEL_5_2

logger = logging.getLogger(__name__)

async def generate_diff_task(resume_id: uuid.UUID):
    """
    Background task to generate an LLM-powered diff and update the resume record.
    """
    logger.info(f"[DIFF_GENERATION_HARNESS] Starting background LLM diff generation for resume: {resume_id}")
    
    try:
        async with AsyncSessionLocal() as db:
            repo = ResumeRepository(db)
            
            # Fetch the optimized resume
            result = await db.execute(select(Resume).where(Resume.id == resume_id))
            optimized_resume = result.scalar_one_or_none()
            
            if not optimized_resume:
                logger.error(f"[DIFF_GENERATION_HARNESS] Resume {resume_id} not found for diff update")
                return

            if not optimized_resume.parent_id:
                logger.warning(f"[DIFF_GENERATION_HARNESS] Resume {resume_id} has no parent_id. Cannot generate diff.")
                return

            # Fetch the parent (original) resume
            parent_result = await db.execute(select(Resume).where(Resume.id == optimized_resume.parent_id))
            parent_resume = parent_result.scalar_one_or_none()
            
            if not parent_resume:
                logger.error(f"[DIFF_GENERATION_HARNESS] Parent resume {optimized_resume.parent_id} not found for diff generation (resume_id: {resume_id})")
                return

            # Get structured data for both
            original_structured = parent_resume.structured_data
            optimized_structured = optimized_resume.structured_data
            
            logger.info(f"[DIFF_GENERATION_HARNESS] [{resume_id}] Structured data loaded. Original size: {len(json.dumps(original_structured))}, Optimized size: {len(json.dumps(optimized_structured))}")

            # Use LLM to generate the diff
            llm = get_model(model_name=MODEL_5_2)
            
            prompt = f"""You are an expert Resume Editor and Recruitment Consultant. Your task is to generate a highly readable, professionally formatted Markdown document that explains PRECISELY how a resume was optimized to match a specific job description.

Your output is for a recruiter who needs to quickly understand the value added by the optimization.

### CRITICAL RULES:
1. **NO PLACEHOLDERS**: Do NOT use placeholder names like "Robert Schupp", "Tech Solutions Inc.", or generic "placeholder" text. Use ONLY the data provided.
2. **Impact-Focused**: Focus on *why* changes were made (e.g., "Added Cloud security keywords to pass ATS filters").
3. **Recruiter-Friendly**: Use bullets, bold text, and clear sections. It should be easy to scan in 30 seconds.
4. **No Word-for-Word Overkill**: Avoid long "Changed from X to Y" blocks unless it's a significant reframing of a summary or a key bullet. For minor skill additions, just list them.

---

### INPUT DATA:

ORIGINAL RESUME DATA (JSON):
{json.dumps(original_structured, indent=2)}

OPTIMIZED RESUME DATA (JSON):
{json.dumps(optimized_structured, indent=2)}

---

### STRUCTURE YOUR RESPONSE AS FOLLOWS:

1. **Overall Optimization Strategy**: 
   - A concise (2-3 sentence) summary of the "vibe" shift. (e.g., "Reframed from a generic developer to a Lead Platform Engineer with a focus on AWS and stakeholder management.")

2. **Key Improvements by Section**:
   - Use Level 3 Headers (### Section Name).
   - Use a bulleted list for specific changes.
   - For each bullet, explain:
     - **What changed**: (Summarize the change)
     - **Why**: (The strategic benefit, e.g., "Aligned with the JD requirement for GCP experience" or "Up-leveled leadership language").
   - If a section didn't change, skip it or say "No changes required."

3. **Strategic Keyword Additions**:
   - List the most important keywords/skills added to the resume that were missing in the original but present in the JD.
   - Categorize them (e.g., Technical, Soft Skills, Certifications).

4. **ATS & Readability Audit**:
   - A brief note on how the formatting or structure was improved for ATS parsers or human readability.

---

### STYLE GUIDELINES:
- Use horizontal rules (`---`) between major sections.
- Use multiple line breaks to keep the document spacious.
- Be professional, direct, and insightful.

Generate the "Resume Optimization Diff" in Markdown format."""
            
            logger.info(f"[DIFF_GENERATION_HARNESS] [{resume_id}] Invoking LLM (MODEL_5_2). Prompt length: {len(prompt)}")
            import time
            start_llm = time.time()
            response = await llm.ainvoke(prompt)
            duration = time.time() - start_llm
            diff_markdown = response.content if hasattr(response, "content") else str(response)
            logger.info(f"[DIFF_GENERATION_HARNESS] [{resume_id}] LLM completed in {duration:.2f}s. Response length: {len(diff_markdown)}")

            # Update the resume record
            current_diff = (optimized_resume.diff or {}).copy()
            current_diff["markdown"] = diff_markdown
            
            if "placeholder" in diff_markdown.lower() or "robert schupp" in diff_markdown.lower():
                 logger.warning(f"[DIFF_GENERATION_HARNESS] [{resume_id}] LLM generated a diff that contains potential placeholder keywords!")

            # We must use the repository to update
            logger.info(f"[DIFF_GENERATION_HARNESS] [{resume_id}] Saving generated diff to database.")
            await repo.update_resume(resume_id, diff=current_diff)
            await db.commit()
            logger.info(f"[DIFF_GENERATION_HARNESS] [{resume_id}] Successfully completed diff generation and updated database.")
                
    except Exception as e:
        logger.error(f"[DIFF_GENERATION_HARNESS] [{resume_id}] Error in generate_diff_task: {str(e)}", exc_info=True)

async def generate_diff(
    request: Request,
    resume_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Testing harness endpoint to manually re-generate and save the diff for a given resume.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        logger.warning(f"Unauthenticated request to generate_diff (harness) for resume {resume_id}")
        raise HTTPException(status_code=401, detail="User not authenticated")

    logger.info(f"Received request (harness) to generate_diff for resume {resume_id} by user {user_id}")

    repo = ResumeRepository(db)
    resume = await repo.get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    # In this new endpoint, we don't strictly enforce org check if it's a testing harness,
    # but for security we should probably check if the user has access to the candidate/org.
    # However, resumes don't have org_id directly. We'd need to check candidate.
    
    if not resume.get("parent_id"):
        raise HTTPException(status_code=400, detail="Resume has no parent. Cannot generate diff.")

    background_tasks.add_task(generate_diff_task, resume_id)

    return {
        "success": True,
        "message": "Diff generation started in the background."
    }
