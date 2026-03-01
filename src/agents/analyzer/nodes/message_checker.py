import logging
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2

logger = logging.getLogger(__name__)

class MessageCheckResult(BaseModel):
    is_satisfactory: bool = Field(..., description="Whether the message is insightful, professional, and includes all required sections.")
    feedback: str = Field(..., description="Detailed feedback if the message is not satisfactory.")

async def message_checker_node(state: AnalyzerState, config: RunnableConfig = None):
    """Checks if the generated message is deep, insightful, and contains all required components."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Checker Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    structured_checker = llm.with_structured_output(MessageCheckResult)
    
    messages = state.get("messages", [])
    if not messages:
        return {"message_feedback": "No message found to check.", "message_retry_count": state.get("message_retry_count", 0) + 1}
        
    current_message = messages[-1]
    
    resume_data = state.get("resume_data", {})
    resume_text = resume_data.get('raw_text') or str(resume_data.get('structured_data', 'No resume data available'))
    job_data = state.get("job_data", {})
    job_text = job_data.get('raw_text', 'No JD text available')
    
    prompt = f"""You are a senior Recruitment Quality Auditor. Your job is to verify if the analysis message provided to the recruiter is high-quality, professional, and contains all necessary components to help them place the candidate.

    ### RESUME TEXT:
    {resume_text}

    ### JOB DESCRIPTION:
    {job_text}

    ### MESSAGE TO AUDIT:
    {current_message}

    ### AUDIT CRITERIA:
    1. **Insight Quality**: Does the 'Overall Impression' provide genuine insight?
    2. **Required Sections**: Are these exact headers present: 'Overall Impression', 'Key Strengths', 'Gaps & Concerns', 'Resume Optimization Hints', 'Candidate Discovery Questions', 'Conclusion/Recommendation'?
    3. **Structural Constraints**:
        - No sub-headers like 'Major Strengths' under the main sections.
        - NO numerical Match Score (e.g., 85/100) included in the text.
    4. **Keyword Check**: Does 'Resume Optimization Hints' suggest missing JD keywords that are implied by the candidate's actual experience? (Verify by cross-referencing Resume and JD).
    5. **Tone & Formatting**: Professional tone, valid Markdown.

    ### QUALITY GUIDELINES:
    - **Accept Tolerance**: Do NOT mark as unsatisfactory for minor phrasing differences, length, or bullets style if the utility is high.
    - **Constructive Only**: Only mark `is_satisfactory=False` for missing sections, redundant headers, inclusion of numerical score, or failure to identify obvious implied keywords/experiences.
    - **Optimization Quality**: Verify that 'Resume Optimization Hints' are explicit and use specific suggestions or probing questions. Ensure they correctly identify and explicitly suggest adding implied skills (like suggesting 'TypeScript' for an 'Angular' dev if TS is in the JD), rather than vague phrasing like 'mention anything that...'.
    - **Pass for High Utility**: If the message helps a recruiter place a person, it should pass.
    """

    try:
        result = await structured_checker.ainvoke(prompt)
        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Checker: is_satisfactory={result.is_satisfactory}")
        
        return {
            "message_feedback": result.feedback if not result.is_satisfactory else None,
            "message_retry_count": state.get("message_retry_count", 0) + (0 if result.is_satisfactory else 1)
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Message Checker failed: {str(e)}", exc_info=True)
        return {"message_feedback": None}
