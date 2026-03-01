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
    minor_gaps: list = None,
    job_text: str = None,
    resume_text: str = None,
    candidate_location: str = None,
    candidate_notes: list = None,
    thread_id: str = NO_THREAD_ID
) -> str:
    """
    Generates a professional markdown write up of the overall impression of this candidate for this job.
    """
    logger.info(f"[ANALYZER] [{thread_id}] Standalone analysis summary generation started.")
    start_time = time.time()
    
    # Organize matches and gaps
    major_hits_text = "\n".join([f"- {h}" for h in major_hits]) if major_hits else "None identified."
    minor_hits_text = "\n".join([f"- {h}" for h in minor_hits]) if minor_hits else "None identified."
    major_gaps_text = "\n".join([f"- {g}" for g in major_gaps]) if major_gaps else "None identified."
    minor_gaps_text = "\n".join([f"- {g}" for g in (minor_gaps or [])]) if minor_gaps else "None identified."
    
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
        "Your goal is to provide a hiring manager with a deep, insightful, and professional markdown write up of the overall impression of this candidate for this job. "
        "Your tone should be professional, analytical, and direct. "
        "Be pragmatic and highlight both strengths and critical missing requirements. "
        "Your insights should help recruiters place people by providing actionable depth.\n\n"
        "# CONSTRAINTS\n"
        "1. Always respond in valid Markdown.\n"
        "2. Maintain a professional and objective tone. Use \"I\" for yourself and address the hiring manager directly or refer to the candidate in the third person.\n"
        "3. Keep your response focused on the match between the resume and the job requirements.\n"
        "4. DO NOT include the numerical Match Score (e.g., 85/100) anywhere in your message. This score is displayed in a separate UI panel.\n"
        "5. Avoid double headers. For example, under '**Key Strengths**', just use bullet points for both major and minor strengths without adding sub-headers like 'Major Strengths'.\n\n"
        "# RESPONSE STRUCTURE\n"
        "Your response MUST include these exact sections in order:\n"
        "1. **Overall Impression**: A deep, 2-3 paragraph professional summary providing insight beyond just repeating hits/gaps.\n"
        "2. **Key Strengths**: A list of why the candidate is a good fit. Use bullet points for both Major and Minor strengths (no sub-headers).\n"
        "3. **Gaps & Concerns**: A list of missing requirements or skills. Use bullet points for both Major and Minor gaps (no sub-headers).\n"
        "4. **Resume Optimization Hints**: Concrete advice on improvements. **CRITICAL: Cross-reference the Job Description against the provided Resume text to identify specific keywords or experiences that are implied by the candidate's existing experience but missing or vague on their resume. "
        "Explicitly identify skills that the candidate almost certainly has given their experience (e.g., if they have 'Angular' experience, they likely have 'TypeScript' skills; if they have 'PostgreSQL' experience, they likely have 'SQL' skills) but haven't explicitly listed, and advise them to add those exact keywords if they are present in the JD. "
        "DO NOT use vague phrasing like 'mention anything that...'. Instead, provide explicit, direct suggestions and specific probing questions for the recruiter to ask the candidate to confirm these implied skills. "
        "Example: 'The JD requires TypeScript. Since you have extensive Angular experience, explicitly add \"TypeScript\" to your skills section to ensure you pass ATS filters.' or 'Ask the candidate if their PostgreSQL experience was on RDS/Aurora; if so, they should state that explicitly.'**\n"
        "5. **Candidate Discovery Questions**: A list of 3-5 high-impact questions the recruiter should ask to probe abilities and address gaps. Mention that updating notes with answers will trigger a re-analysis.\n"
        "6. **Conclusion/Recommendation**: A brief final thought on whether to proceed."
    )

    user_message = f"""Please provide an overall impression for this candidate:
- **JOB DESCRIPTION**: {job_text}
- **RESUME TEXT**: {resume_text}
- **CANDIDATE INFO**: {candidate_info}

### IDENTIFIED MAJOR STRENGTHS
{major_hits_text}

### IDENTIFIED MINOR STRENGTHS
{minor_hits_text}

### IDENTIFIED MAJOR GAPS
{major_gaps_text}

### IDENTIFIED MINOR GAPS
{minor_gaps_text}
"""

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
    job_data = state.get("job_data", {})
    job_text = job_data.get('raw_text', 'No JD text available')
    
    resume_data = state.get("resume_data", {})
    resume_text = resume_data.get('raw_text') or str(resume_data.get('structured_data', 'No resume data available'))

    try:
        summary_msg = await generate_analysis_summary(
            score=score,
            major_hits=major_hits,
            minor_hits=minor_hits,
            major_gaps=major_gaps,
            minor_gaps=minor_gaps,
            job_text=job_text,
            resume_text=resume_text,
            candidate_location=candidate_location,
            candidate_notes=candidate_notes,
            thread_id=clean_id_str
        )
        
        # Append personal info mismatch question if it exists
        mismatch_question = state.get("personal_info_mismatch_question")
        if mismatch_question:
            summary_msg += f"\n\n---\n\n{mismatch_question}"

        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Node completed.")
        
        return {
            "messages": state.get("messages", []) + [summary_msg],
            "message_retry_count": 0 # Initialize or reset retry count
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Message Node failed: {str(e)}", exc_info=True)
        raise e
