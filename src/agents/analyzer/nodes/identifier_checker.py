import logging
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2

logger = logging.getLogger(__name__)

class IdentifierCheckResult(BaseModel):
    is_accurate: bool = Field(..., description="Whether the identified hits and gaps are accurate and not hallucinated.")
    feedback: str = Field(..., description="Detailed feedback if the identification is not accurate or has hallucinations.")

async def identifier_checker_node(state: AnalyzerState, config: RunnableConfig = None):
    """Checks if the identified hits and gaps are accurate and reasonable."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Checker Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    structured_checker = llm.with_structured_output(IdentifierCheckResult)
    
    resume_data = state["resume_data"]
    job_data = state["job_data"]
    resume_text = resume_data.get('raw_text') or str(resume_data.get('structured_data', 'No resume data available'))
    job_text = job_data.get('raw_text', 'No JD text available')
    
    major_hits = state.get("major_hits", [])
    minor_hits = state.get("minor_hits", [])
    major_gaps = state.get("major_gaps", [])
    minor_gaps = state.get("minor_gaps", [])
    
    prompt = f"""You are a Senior ATS Auditor. Your job is to verify if the matches (hits) and gaps identified by another agent are accurate, well-supported by the provided Resume and Job Description, and free of hallucinations.

    ### JOB DESCRIPTION:
    {job_text}
    
    ### RESUME TEXT/DATA:
    {resume_text}
    
    ### IDENTIFIED HITS:
    - **MAJOR HITS**: {major_hits}
    - **MINOR HITS**: {minor_hits}
    
    ### IDENTIFIED GAPS:
    - **MAJOR GAPS**: {major_gaps}
    - **MINOR GAPS**: {minor_gaps}

    ### TASK:
    1. Cross-reference every identified hit and gap with the Resume and Job Description.
    2. Check for "hallucinations" (skills or experiences claimed to be present or missing that are not supported by the text).
    3. Ensure the categorization (Major vs. Minor) follows the standard logic (e.g., missing core tech is a MAJOR gap, missing preferred skill is a MINOR gap).

    **Guidelines for Satisfactory Review**:
    - **Accept Tolerance**: Minor omissions or slight differences in categorization (e.g., Hit vs. Minor Hit) that do not change the candidate's core profile should NOT trigger a repair.
    - **Focus on Errors**: Only mark `is_accurate=False` for hallucinations, major missed requirements, or serious miscategorizations.
    - **Constructive Feedback**: If not accurate, provide specific details on what to correct.

    Consistency and accuracy are paramount.
    """

    try:
        result = await structured_checker.ainvoke(prompt)
        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Checker: is_accurate={result.is_accurate}")
        
        return {
            "identifier_feedback": result.feedback if not result.is_accurate else None,
            "identifier_retry_count": state.get("identifier_retry_count", 0) + (0 if result.is_accurate else 1)
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Checker failed: {str(e)}", exc_info=True)
        return {"identifier_feedback": None}
