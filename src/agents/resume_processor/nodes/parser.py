import logging

from langchain_core.runnables import RunnableConfig

from ....agents.resume_processor.state import ResumeState
from ....agents.utils import get_checkpoint_config, get_thread_id, strip_id_prefix
from ....constants import NO_THREAD_ID, CONFIG_THREAD_ID_KEY
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.resume import ResumeSchema
from ....agents.checkpointer import get_checkpointer

logger = logging.getLogger(__name__)

async def parser_node(state: ResumeState, config: RunnableConfig = None):
    """
    Extracts structured data from the raw resume text using LLM,
    and manages personal info in User Notes.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)

    logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Parser Node started.")
    
    if thread_id_str != NO_THREAD_ID:
        pass
    raw_text = state.get("raw_text")
    if not raw_text:
        raise RuntimeError("No raw_text found in state for parser_node")

    # Use the latest powerful model for parsing to ensure high quality extraction
    llm = get_model(model_name=MODEL_5_2)
    structured_llm = llm.with_structured_output(ResumeSchema)
    
    enhanced_prompt = f"""You are a world-class Resume Parsing Engine. Your goal is to extract every meaningful piece of information from the provided resume text into a structured format.

# CRITICAL INSTRUCTIONS:
1. **CAPTURE ALL INFO**: Do not miss anything. Extract name, email, phone, linkedin, location, all experience, education, skills, projects, etc.
2. **NO TRUNCATION**: Capture every single bullet point, project detail, and skill. Do not summarize.
3. **CONTACT INFO**: Rigorously look for Name, Email, Phone, LinkedIn, and Location/Address in the header.
4. **WORK EXPERIENCE**: 
    - Extract ALL roles, companies, and date ranges.
    - Preserve complete bullet points, including specific metrics, technologies, and achievements.
5. **EDUCATION**: Capture degrees, institutions, graduation dates, and relevant coursework or honors.
6. **SKILLS**: Extract a comprehensive list of technical skills, tools, languages, and frameworks.
7. **PROJECTS**: Look for and extract: Personal Projects, AI Projects, Open Source, and Side Hustles. Capture name, description, and technologies used.
8. **MISC**: Extract Military Service, Interests, Certifications, Patents, Publications, and Awards sections.

# Resume text:
{raw_text}"""

    try:
        # Broadcast status
        from ....api.ws.manager import manager
        import json
        job_id = state.get("job_id")
        resume_id = state.get("resume_id")
        if job_id:
            await manager.broadcast_to_job(
                json.dumps({
                    "status": "Parsing",
                    "message": "Extracting structured data from resume...",
                    "resume_id": str(resume_id),
                    "completed": False
                }),
                str(job_id)
            )

        # Check for cancellation before LLM call
        import asyncio
        checkpointer = get_checkpointer()
        thread_id = config.get("configurable", {}).get(CONFIG_THREAD_ID_KEY)
        config_check = get_checkpoint_config(thread_id)
        checkpoint_tuple = await checkpointer.aget_tuple(config_check)
        if checkpoint_tuple and checkpoint_tuple.metadata.get("status") == "cancelled":
            raise asyncio.CancelledError("Resume processing was cancelled")
        
        structured_data = await structured_llm.ainvoke(enhanced_prompt)
        structured_dict = structured_data.model_dump()

        # Handle Personal Info / User Notes - Removed as UserNote is gone
        contact = structured_dict.get("contact", {})
        mismatch_question = None
        
        # Validate minimum data quality
        experience = structured_dict.get("experience", [])

        if not contact.get("name") and not contact.get("email"):
            logger.warning(f"[RESUME_PROCESSOR] [{clean_id_str}] Parser produced no contact info")
            
        if not experience or len(experience) == 0:
            logger.warning(f"[RESUME_PROCESSOR] [{clean_id_str}] Parser found no work experience")

        # Add quality metrics to metadata
        quality_score = 0
        if contact.get("name"): quality_score += 1
        if contact.get("email"): quality_score += 1
        if contact.get("phone"): quality_score += 0.5
        if len(experience) > 0: quality_score += 2
        if structured_dict.get("education"): quality_score += 1

        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Parser quality score: {quality_score}/5.5")

        logger.info(f"[RESUME_PROCESSOR] [{clean_id_str}] Parser Node completed.")
        return {
            "structured_data": structured_dict,
            "personal_info_mismatch_question": mismatch_question,
            "metadata": {
                **state.get("metadata", {}),
                "parse_quality": quality_score
            }
        }
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"[RESUME_PROCESSOR] [{clean_id_str}] Parser Node failed: {str(e)}", exc_info=True)
        raise e
