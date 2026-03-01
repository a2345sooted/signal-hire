import logging
import time

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_4O_MINI
from ....constants import NO_THREAD_ID

logger = logging.getLogger(__name__)

async def hiring_notes_node(state: AnalyzerState, config: RunnableConfig = None):
    """
    Generates a 'hiring notes' section that provides ammunition for the recruiter
    to use with the hiring team.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)

    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Hiring Notes Node started.")
    start_time = time.time()
    
    score = state.get("score", 0)
    major_hits = state.get("major_hits", [])
    minor_hits = state.get("minor_hits", [])
    major_gaps = state.get("major_gaps", [])
    minor_gaps = state.get("minor_gaps", [])
    candidate_location = state.get("candidate_location")
    candidate_notes = state.get("candidate_notes", [])
    messages = state.get("messages", [])
    analysis_message = messages[-1] if messages else "No analysis message available"

    job_data = state.get("job_data", {})
    job_text = job_data.get('raw_text', 'No JD text available')
    
    resume_data = state.get("resume_data", {})
    resume_text = resume_data.get('raw_text') or str(resume_data.get('structured_data', 'No resume data available'))

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

    system_prompt = (
        "You are Aline, a professional recruitment consultant at Signal-Hire. "
        "Your goal is to provide a recruiter with 'ammunition' (strategic talking points) to use with the HIRING TEAM to get them interested in this candidate for this specific role. "
        "The audience for these notes is the HIRING MANAGER and the engineering/hiring team. "
        "Focus on the strongest selling points, how they solve the team's pain points, and why they are a top choice despite any minor gaps. "
        "Provide persuasive justifications for moving to interview. "
        "Utilize any available candidate notes, location, and previous analysis summary to provide deep, strategic insights. "
        "Your tone should be persuasive, insightful, and strategic. "
        "Provide a concise but powerful list of talking points designed to 'sell' the candidate's value proposition to the hiring team."
    )

    user_message = f"""Please provide hiring notes (recruiter ammunition) for this candidate:
- **JOB DESCRIPTION**: {job_text}
- **RESUME TEXT**: {resume_text}
- **CANDIDATE INFO**: {candidate_info}
- **ANALYSIS SUMMARY**: {analysis_message}
- **Match Score**: {score}/100

### IDENTIFIED MAJOR STRENGTHS
{major_hits_text}

### IDENTIFIED MINOR STRENGTHS
{minor_hits_text}

### IDENTIFIED MAJOR GAPS
{major_gaps_text}

### IDENTIFIED MINOR GAPS
{minor_gaps_text}

Provide the response in Markdown bullet points.
"""

    llm = get_model(model_name=MODEL_4O_MINI, temperature=0.0)
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message)
    ]

    try:
        response = await llm.ainvoke(messages)
        duration = time.time() - start_time
        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Hiring Notes Node completed in {duration:.2f}s.")
        
        return {
            "hiring_notes": response.content.strip()
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Hiring Notes Node failed: {str(e)}", exc_info=True)
        # We don't want to fail the whole process if hiring notes fail
        return {"hiring_notes": "Could not generate hiring notes."}
