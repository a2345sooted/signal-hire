import logging
from langchain_core.runnables import RunnableConfig

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.analysis import MatchGapAnalysisSchema

logger = logging.getLogger(__name__)

async def identifier_repairer_node(state: AnalyzerState, config: RunnableConfig = None):
    """Repairs the identified hits and gaps based on feedback from the checker."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Repairer Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    structured_repairer = llm.with_structured_output(MatchGapAnalysisSchema)
    
    resume_data = state["resume_data"]
    job_data = state["job_data"]
    resume_text = resume_data.get('raw_text') or str(resume_data.get('structured_data', 'No resume data available'))
    job_text = job_data.get('raw_text', 'No JD text available')
    
    major_hits = state.get("major_hits", [])
    minor_hits = state.get("minor_hits", [])
    major_gaps = state.get("major_gaps", [])
    minor_gaps = state.get("minor_gaps", [])
    feedback = state.get("identifier_feedback")
    
    prompt = f"""You are an expert ATS Analyzer. Your objective is to REVISE the identified hits and gaps based on critical feedback from an auditor.

    ### JOB DESCRIPTION:
    {job_text}
    
    ### RESUME TEXT/DATA:
    {resume_text}
    
    ### PREVIOUS ATTEMPT:
    - **MAJOR HITS**: {major_hits}
    - **MINOR HITS**: {minor_hits}
    - **MAJOR GAPS**: {major_gaps}
    - **MINOR GAPS**: {minor_gaps}

    ### CRITICAL FEEDBACK FROM AUDITOR:
    {feedback}

    ### TASK:
    1. Review the feedback carefully.
    2. Re-analyze the Resume and Job Description to address the auditor's concerns.
    3. Provide a revised, accurate list of hits and gaps, ensuring no hallucinations and correct categorization.
    """

    try:
        result = await structured_repairer.ainvoke(prompt)
        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Repairer Node completed.")
        
        return {
            "major_hits": result.major_hits,
            "minor_hits": result.minor_hits,
            "major_gaps": result.major_gaps,
            "minor_gaps": result.minor_gaps,
            "identifier_feedback": None # Clear feedback after repair
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Repairer Node failed: {str(e)}", exc_info=True)
        return {}
