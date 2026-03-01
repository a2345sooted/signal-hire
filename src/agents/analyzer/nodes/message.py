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
    candidate_location: str = None,
    candidate_notes: list = None,
    thread_id: str = NO_THREAD_ID
) -> str:
    """
    Generates a professional markdown write up of the overall impression of this candidate for this job.
    """
    logger.info(f"[ANALYZER] [{thread_id}] Standalone analysis summary generation started.")
    start_time = time.time()
    
    # Take a few examples from each to provide context to the LLM
    hits_sample = (major_hits + minor_hits)
    gaps_sample = major_gaps
    
    candidate_info = f"Location: {candidate_location or 'Not specified'}\n"
    if candidate_notes:
        candidate_info += "Notes:\n"
        for note in candidate_notes:
            content = note.get('content', '')
            candidate_info += f"- {content}\n"
    
    # Use the same structure and role/constraints format as respond.py for better results
    system_prompt = (
        "# ROLE\n"
        "You are Aline, a professional recruitment consultant at Signal-Hire. "
        "Your goal is to provide a hiring manager with a clear, objective, and professional markdown write up of the overall impression of this candidate for this job. "
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
        "Your response should be a structured markdown write-up including:\n"
        "- **Overall Impression**: A 1-2 paragraph professional summary of the candidate's suitability for the role.\n"
        "- **The Match Score**: (e.g., 85/100).\n"
        "- **Key Strengths/Matches**: Why the candidate is a good fit.\n"
        "- **Critical Gaps/Concerns**: Important requirements or skills that are missing.\n"
        "- **Conclusion/Recommendation**: A brief final thought on whether to interview or not."
    )

    user_message = f"""Please provide an overall impression for this candidate:
- **CANDIDATE INFO**: {candidate_info}
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
        logger.info(f"[ANALYZER] [{thread_id}] Analysis summary LLM call started.")
        response = await llm.ainvoke(messages)
        logger.info(f"[ANALYZER] [{thread_id}] Analysis summary LLM call completed.")
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
    candidate_location = state.get("candidate_location")
    candidate_notes = state.get("candidate_notes", [])

    try:
        summary_msg = await generate_analysis_summary(
            score=score,
            major_hits=major_hits,
            minor_hits=minor_hits,
            major_gaps=major_gaps,
            candidate_location=candidate_location,
            candidate_notes=candidate_notes,
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
