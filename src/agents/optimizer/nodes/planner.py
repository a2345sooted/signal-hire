import logging
import json
from langchain_core.runnables import RunnableConfig
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.resume import OptimizationPlanSchema
from ..state import OptimizerState
from ....agents.utils import strip_id_prefix, get_thread_id

logger = logging.getLogger(__name__)

async def planner_node(state: OptimizerState, config: RunnableConfig = None):
    """
    Analyzes the JD, Resume, and Analysis to create a concrete optimization plan.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Planner Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    structured_llm = llm.with_structured_output(OptimizationPlanSchema)
    
    job_data = state.get("job_data", {})
    resume_data = state.get("resume_data", {})
    analysis_data = state.get("analysis_data", {})
    
    job_text = job_data.get("raw_text") or json.dumps(job_data.get("structured_data", {}))
    resume_text = resume_data.get("raw_text") or json.dumps(resume_data.get("structured_data", {}))
    analysis_content = analysis_data.get("content", {})
    analysis_message = analysis_content.get("message", "No previous analysis summary available.")
    hiring_notes = analysis_content.get("hiring_notes", "No previous hiring notes available.")

    prompt = f"""You are a Strategic Career Coach and ATS Specialist. Your goal is to create a detailed PLAN to optimize a candidate's resume for a specific Job Description.

JOB DESCRIPTION:
{job_text}

CANDIDATE RESUME:
{resume_text}

PREVIOUS MATCH ANALYSIS SUMMARY:
{analysis_message}

PREVIOUS HIRING NOTES & OPTIMIZATION THOUGHTS:
{hiring_notes}

TASK:
1. Identify specific bullet points in the resume that should be rewritten to better mirror the JD's language while remaining truthful.
2. List skills from the resume that should be emphasized or brought to the top.
3. List critical skills mentioned in the JD that are missing from the resume (to be added if the candidate likely has them or to highlight as gaps).
4. Identify high-value ATS keywords from the JD that should be integrated.
5. Summarize the major gaps and strong sections.

Create a comprehensive Optimization Plan.
"""

    try:
        plan = await structured_llm.ainvoke(prompt)
        logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Planner Node completed.")
        
        return {
            "optimization_plan": plan,
            "messages": state.get("messages", []) + ["Optimization plan created."]
        }
    except Exception as e:
        logger.error(f"[OPTIMIZER_AGENT] [{clean_id_str}] Planner Node failed: {str(e)}", exc_info=True)
        raise e
