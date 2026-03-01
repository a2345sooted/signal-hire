import logging
from langchain_core.runnables import RunnableConfig
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.job import JobDetailsSchema
from ..state import JDState

logger = logging.getLogger(__name__)

async def extract_details_node(state: JDState, config: RunnableConfig = None):
    """
    Extracts structured job details (pay, location, employment type, etc.) from the JD.
    """
    job_id = state.get("job_id")
    logger.info(f"[JD_PROCESSOR] [{job_id}] Extracting job details...")

    llm = get_model(model_name=MODEL_5_2)
    structured_llm = llm.with_structured_output(JobDetailsSchema)

    raw_text = state.get("raw_text")

    prompt = f"""You are an expert recruitment data analyst. Your task is to extract specific job details from the provided Job Description (JD).

JD TEXT:
{raw_text}

EXTRACT THE FOLLOWING FIELDS:
1. pay_range_min: Minimum salary or hourly rate (as an integer).
2. pay_range_max: Maximum salary or hourly rate (as an integer).
3. pay_type: 'salary' or 'hourly'.
4. employment_type: A list containing one or more of: 'fte', 'c2c', 'w2'.
5. location: The specific city and state mentioned, or 'Remote'.
6. arrangement: 'on-site', 'remote', or 'hybrid'.
7. hybrid_days_week: If hybrid, how many days per week are required in office (integer).
8. offers_relocation: Boolean, true if the JD explicitly mentions relocation assistance.

If a field cannot be found or reasonably inferred, leave it as null/None (except for booleans which should be false if not mentioned, and lists which should be empty).
"""

    try:
        details = await structured_llm.ainvoke(prompt)
        logger.info(f"[JD_PROCESSOR] [{job_id}] Job details extracted successfully.")
        
        details_dict = details.model_dump()
        return {
            "details": details_dict
        }
    except Exception as e:
        logger.error(f"[JD_PROCESSOR] [{job_id}] Failed to extract job details: {str(e)}", exc_info=True)
        # Don't fail the whole graph if detail extraction fails
        return {"details": {}}
