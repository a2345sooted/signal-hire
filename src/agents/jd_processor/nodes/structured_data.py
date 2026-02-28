import logging
import asyncio

from langchain_core.runnables import RunnableConfig

from ....agents.jd_processor.state import JDState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....constants import NO_THREAD_ID
from ....ai_model_factory import get_model, MODEL_4O_MINI
from ....models.job import JobSchema

logger = logging.getLogger(__name__)

async def structured_data_node(state: JDState, config: RunnableConfig = None):
    thread_id_str = get_thread_id(state, config)
    
    # If it's the thread_id, it might have a prefix (e.g., jd_)
    clean_id_str = strip_id_prefix(thread_id_str)

    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Structured Data Node started.")
    import time
    start_time = time.time()
    
    # Freeze input at node entry
    raw_text = state['raw_text']
    
    llm = get_model(model_name=MODEL_4O_MINI)
    structured_llm = llm.with_structured_output(JobSchema)
    
    prompt = f"""Extract and analyze structured information from the following job description text.
Respond ONLY with the JSON object.

CRITICAL INSTRUCTIONS:
- Extract company name and job title if present.
- Populate 'requirements' with 'responsibilities', 'must_have', 'nice_to_have' (concise strings).
- 'skills' should be a flat list of technical/soft skills.
- ANALYSIS:
    - Identify core technologies.
    - Experience level (Senior, Principal, etc.).
    - ATS keywords.
- 'raw_text' must be preserved as the original input.

Job Description:
{raw_text}"""
    
    try:
        logger.debug(f"[JD_PROCESSOR] [{clean_id_str}] Structured Data LLM invocation started.")
        result = await structured_llm.ainvoke(prompt)
        duration = time.time() - start_time
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Structured Data LLM completed in {duration:.2f}s.")
        
        # Ensure raw_text is preserved
        result.raw_text = raw_text
        
        
        logger.debug(f"[JD_PROCESSOR] [{clean_id_str}] Structured Data Node result: {result.model_dump_json(indent=2)}")
        
        # Ensure 'job_title' is available for display purposes if 'title' was used in extraction
        structured_data = result.model_dump()
        if "title" in structured_data:
            structured_data["job_title"] = structured_data["title"]

        return {
            "structured_data": structured_data
        }
    except Exception as e:
        logger.error(f"[JD_PROCESSOR] [{clean_id_str}] Structured Data Node failed: {str(e)}", exc_info=True)
        raise e
