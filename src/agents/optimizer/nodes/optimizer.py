import logging
import json
from langchain_core.runnables import RunnableConfig
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.resume import ResumeSchema
from ..state import OptimizerState
from ....agents.utils import strip_id_prefix, get_thread_id

logger = logging.getLogger(__name__)

async def optimizer_node(state: OptimizerState, config: RunnableConfig = None):
    """
    Executes the optimization plan to produce a new structured resume.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Optimizer Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    structured_llm = llm.with_structured_output(ResumeSchema)
    
    job_data = state.get("job_data", {})
    resume_data = state.get("resume_data", {})
    plan = state.get("optimization_plan")
    
    if not plan:
        raise RuntimeError(f"[OPTIMIZER_AGENT] [{clean_id_str}] Missing optimization plan.")

    resume_structured = resume_data.get("structured_data", {})
    job_text = job_data.get("raw_text") or json.dumps(job_data.get("structured_data", {}))
    plan_json = plan.model_dump_json(indent=2)

    prompt = f"""You are an expert Resume Writer. Your task is to rewrite the candidate's structured resume data based on a specific Job Description and an Optimization Plan.

JOB DESCRIPTION:
{job_text}

ORIGINAL RESUME DATA:
{json.dumps(resume_structured, indent=2)}

OPTIMIZATION PLAN:
{plan_json}

INSTRUCTIONS:
1.  **Strict Adherence**: Follow the Optimization Plan closely.
2.  **Truthfulness**: Do NOT invent new experiences or titles. Only rewrite existing bullets to better highlight relevant skills and impact using keywords from the JD.
3.  **ATS Optimization**: Integrate the suggested ATS keywords and skills naturally.
4.  **Formatting**: Ensure the output is a perfectly valid and complete ResumeSchema object.
5.  **Experience**: Update the 'bullets' in the experience section as suggested in the plan.
6.  **Summary**: Rewrite the professional summary to better align with the target role.
7.  **Skills**: Update the skills list to include missing but relevant skills identified in the plan.

Generate the optimized structured resume.
"""

    try:
        optimized_resume = await structured_llm.ainvoke(prompt)
        logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Optimizer Node completed.")
        
        return {
            "optimized_resume": optimized_resume,
            "messages": state.get("messages", []) + ["Optimized resume generated."]
        }
    except Exception as e:
        logger.error(f"[OPTIMIZER_AGENT] [{clean_id_str}] Optimizer Node failed: {str(e)}", exc_info=True)
        raise e
