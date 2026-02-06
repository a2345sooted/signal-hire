import logging
import time

from langchain_core.runnables import RunnableConfig

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2, MODEL_4O_MINI
from ....constants import NO_THREAD_ID

logger = logging.getLogger(__name__)

async def generate_analysis_summary(
    score: int, 
    major_hits: list, 
    minor_hits: list, 
    major_gaps: list, 
    thread_id: str = NO_THREAD_ID
) -> str:
    """
    Generates a concise summary of the analysis with a targeted question about a gap.
    """
    logger.info(f"[ANALYZER] [{thread_id}] Standalone analysis summary generation started.")
    start_time = time.time()
    
    # Take a few examples from each to provide context to the LLM
    hits_sample = (major_hits + minor_hits)[:4]
    gaps_sample = major_gaps[:3]
    
    # Use the same structure and role/constraints format as respond.py for better results
    system_prompt = (
        "# ROLE\n"
        "You are Aline, a professional recruitment consultant at Signal-Hire. "
        "Your goal is to provide a hiring manager with a clear, objective analysis of how well a candidate's resume matches a specific job description. "
        "Your tone should be professional, analytical, and direct. "
        "Be pragmatic and highlight both strengths and critical missing requirements. "
        "Your insights should help the hiring manager decide whether to proceed with this candidate.\n\n"
        "# CONSTRAINTS\n"
        "1. Always respond in valid Markdown.\n"
        "2. Maintain a professional and objective tone. Use \"I\" for yourself and address the hiring manager directly or refer to the candidate in the third person.\n"
        "3. Keep your response focused on the match between the resume and the job requirements.\n"
        "4. End with a single, targeted, actionable recommendation or a question for the hiring manager to consider during an interview.\n"
        "5. Use the exact ATS Score provided in the input. Do not make up a different score.\n\n"
        "# RESPONSE CONTENT\n"
        "Your response should include:\n"
        "- The Match Score (e.g., 85/100).\n"
        "- A summary of why the candidate is a good fit (Key Matches).\n"
        "- A summary of critical Gaps or concerns the hiring manager should be aware of."
    )

    user_message = f"""Please analyze this candidate for the hiring manager:
- **Match Score**: {score}/100
- **Key Matches**: {hits_sample}
- **Critical Gaps**: {gaps_sample}"""

    llm = get_model(model_name=MODEL_4O_MINI, temperature=0.0)
    
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]

    try:
        response = await llm.ainvoke(messages)
        duration = time.time() - start_time
        logger.info(f"[ANALYZER] [{thread_id}] Standalone analysis summary generation completed in {duration:.2f}s")
        return response.content.strip()
    except Exception as e:
        logger.error(f"[ANALYZER] [{thread_id}] Analysis summary generation failed: {str(e)}", exc_info=True)
        raise e

async def message_node(state: AnalyzerState, config: RunnableConfig = None):
    """
    Generates the analysis summary message and stores it in the state.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)

    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Node started.")
    
    if clean_id_str != NO_THREAD_ID:
        pass

    score = state.get("score", 0)
    major_hits = state.get("major_hits", [])
    minor_hits = state.get("minor_hits", [])
    major_gaps = state.get("major_gaps", [])
    minor_gaps = state.get("minor_gaps", [])

    try:
        # Broadcast status
        from ....api.ws.manager import manager
        import json
        job_id = state.get("job_id")
        resume_id = state.get("resume_id")
        if job_id:
            await manager.broadcast_to_job(
                json.dumps({
                    "status": "Summarizing",
                    "message": "Generating analysis summary...",
                    "resume_id": str(resume_id),
                    "completed": False
                }),
                str(job_id)
            )

        summary_msg = await generate_analysis_summary(
            score,
            major_hits,
            minor_hits,
            major_gaps,
            thread_id=clean_id_str
        )
        
        # Append personal info mismatch question if it exists
        mismatch_question = state.get("personal_info_mismatch_question")
        if mismatch_question:
            summary_msg += f"\n\n---\n\n{mismatch_question}"

        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Node completed.")
        
        # Ensure chat input is re-enabled after the message node finishes
        if clean_id_str != NO_THREAD_ID:
            pass
            
        return {"messages": state.get("messages", []) + [summary_msg]}
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Message Node failed: {str(e)}", exc_info=True)
        raise e
