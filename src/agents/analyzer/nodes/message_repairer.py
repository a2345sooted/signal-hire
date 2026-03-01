import logging
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_4O_MINI

logger = logging.getLogger(__name__)

async def message_repairer_node(state: AnalyzerState, config: RunnableConfig = None):
    """Repairs the generated message based on feedback from the checker."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Repairer Node started.")
    
    llm = get_model(model_name=MODEL_4O_MINI, temperature=0.0)
    
    messages = state.get("messages", [])
    current_message = messages[-1] if messages else "No previous message found."
    feedback = state.get("message_feedback", "No feedback provided.")
    
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
    
    # Organize matches and gaps for context
    major_hits_text = "\n".join([f"- {h}" for h in major_hits]) if major_hits else "None identified."
    minor_hits_text = "\n".join([f"- {h}" for h in minor_hits]) if minor_hits else "None identified."
    major_gaps_text = "\n".join([f"- {g}" for g in major_gaps]) if major_gaps else "None identified."
    minor_gaps_text = "\n".join([f"- {g}" for g in minor_gaps]) if minor_gaps else "None identified."
    
    candidate_info = f"Location: {candidate_location or 'Not specified'}\n"
    if candidate_notes:
        candidate_info += "Notes:\n"
        for note in candidate_notes:
            content = note.get('content', '')
            candidate_info += f"- {content}\n"

    system_prompt = (
        "You are Aline, a professional recruitment consultant. You are tasked with REPAIRING an analysis message based on critical feedback from an auditor. "
        "The goal is to ensure the message is deep, insightful, professional, and follows the strict structure requirements.\n\n"
        "REQUIRED SECTIONS (MUST include these exact headers):\n"
        "1. **Overall Impression**\n"
        "2. **Key Strengths** (bullet points only, no sub-headers)\n"
        "3. **Gaps & Concerns** (bullet points only, no sub-headers)\n"
        "4. **Resume Optimization Hints** (CRITICAL: Identify keywords or experiences from JD implied by candidate's experience but missing or vague on Resume. Explicitly identify and suggest adding implied skills like 'TypeScript' if they have 'Angular' experience, etc. Use explicit suggestions and specific probing questions for the recruiter to ask the candidate. DO NOT use vague 'mention anything that' phrasing.)\n"
        "5. **Candidate Discovery Questions**\n"
        "6. **Conclusion/Recommendation**\n\n"
        "CONSTRAINTS:\n"
        "1. Maintain a professional tone and address the hiring manager directly.\n"
        "2. Fix ONLY the issues mentioned in the feedback.\n"
        "3. DO NOT include the numerical Match Score (e.g., 85/100) in the message.\n"
        "4. Avoid double headers like 'Major Strengths' under 'Key Strengths'."
    )
    
    user_prompt = f"""
    ### ORIGINAL DATA:
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

    ### PREVIOUS ATTEMPTED MESSAGE:
    {current_message}

    ### CRITICAL FEEDBACK FROM AUDITOR:
    {feedback}

    Please provide a REVISED version of the analysis message that addresses the feedback while following the structure perfectly.
    """

    try:
        repair_messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        response = await llm.ainvoke(repair_messages)
        
        # Append personal info mismatch question if it exists and was removed in repair
        mismatch_question = state.get("personal_info_mismatch_question")
        revised_msg = response.content.strip()
        if mismatch_question and mismatch_question not in revised_msg:
             revised_msg += f"\n\n---\n\n{mismatch_question}"

        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Message Repairer Node completed.")
        
        # We replace the last message with the repaired one
        updated_messages = list(messages)
        if updated_messages:
            updated_messages[-1] = revised_msg
        else:
            updated_messages = [revised_msg]
            
        return {
            "messages": updated_messages,
            "message_feedback": None # Clear feedback after repair
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Message Repairer Node failed: {str(e)}", exc_info=True)
        return {}
