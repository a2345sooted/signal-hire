import logging

from langchain_core.runnables import RunnableConfig

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....constants import NO_THREAD_ID
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.analysis import MatchGapAnalysisSchema

logger = logging.getLogger(__name__)

async def identifier_node(state: AnalyzerState, config: RunnableConfig = None):
    """Identifies matches and gaps between the resume and the job description."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Node started.")
    
    if clean_id_str != NO_THREAD_ID:
        pass

    llm = get_model(model_name=MODEL_5_2)
    structured_identifier = llm.with_structured_output(MatchGapAnalysisSchema)
    
    resume_data = state["resume_data"]
    job_data = state["job_data"]
    candidate_location = state.get("candidate_location")
    candidate_notes = state.get("candidate_notes", [])
    
    resume_text = resume_data.get('raw_text') or str(resume_data.get('structured_data', 'No resume data available'))
    job_text = job_data.get('raw_text', 'No JD text available')
    
    candidate_info = f"Location: {candidate_location or 'Not specified'}\n"
    if candidate_notes:
        candidate_info += "Notes:\n"
        for note in candidate_notes:
            content = note.get('content', '')
            candidate_info += f"- {content}\n"

    prompt = f"""You are an expert ATS (Applicant Tracking System) Analyzer. Your task is to perform a rigorous, objective, and detailed comparison between a Resume and a Job Description.
    
    CANDIDATE INFO:
    {candidate_info}

    JOB DESCRIPTION:
    {job_text}
    
    RESUME TEXT/DATA:
    {resume_text}
    
    SCORING RUBRIC (FOR YOUR REFERENCE TO IDENTIFY HITS/GAPS):
    1. Skills Match (30 pts): Hard skills (languages, tools, platforms).
    2. Experience Relevance (25 pts): Title, industry, and day-to-day responsibilities.
    3. Seniority / Years of Experience (15 pts): Required vs. actual.
    4. Education & Certifications (10 pts): Degree field + level; relevant certs.
    5. Keyword / ATS Coverage (10 pts): Phrasing, titles, and terminology overlap.
    6. Accomplishments vs. Responsibilities (5 pts): Quantified impact vs. just listing duties.
    7. Formatting & Clarity (5 pts): Clean, readable, ATS-compatible format.

    CRITICAL INSTRUCTIONS:
    1.  **Exclude Non-Skill Factors**: Do NOT identify gaps or hits for things like visa sponsorship, hybrid/remote work preferences, location, or general language literacy (e.g., "Advanced English") unless it is the *primary* function of the role (e.g., Translator, Technical Writer). These are almost never MAJOR gaps.
    2.  **Node.js Recognition**: When identifying technology matches, be aware of variations in naming for Node.js. "Node.js", "NodeJS", "Nodejs", and "Node" (in a web development context) should all be treated as the same technology. Ensure you check for these variations in both the JD and the Resume.
    3.  **Categorization Guidelines**:
        *   **Major Hits**: Exact experience match, specialized skills required, significantly exceeding requirements, domain expertise, proven track record in JD goals.
        *   **Minor Hits**: Adjacent/related skills, learning trajectory toward required skills, soft skills mentioned in JD, cultural fit indicators.
        *   **Major Gaps**: Missing core programming language/technology, missing required certification/license, not meeting minimum years of experience, missing required degree (if mandatory). NEVER mark general language proficiency as a MAJOR gap.
        *   **Minor Gaps**: Missing preferred (not required) skill, lacks familiarity with specific tool (but has similar), doesn't have all nice-to-have qualifications, slightly below experience threshold (< 1 year), or missing evidence of a standard language requirement (like English) when it's not the primary role.
    3.  **Realistic Assessment**: If a candidate's experience strongly implies a skill through context, you may consider it a match.
    4.  **Evidence-Based**: Every hit or gap you identify must be rooted in the provided text or strong context.
    5.  **No Scoring**: Do NOT attempt to calculate a numerical score. Your focus is exclusively on the qualitative comparison.

    Consistency is paramount. Treat every requirement in the JD as a checklist item.
    """

    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Node: extracted texts. Starting LLM call...")
    
    try:
        result = await structured_identifier.ainvoke(prompt)
        
        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Node: LLM call completed.")
        
        return {
            "major_hits": result.major_hits,
            "minor_hits": result.minor_hits,
            "major_gaps": result.major_gaps,
            "minor_gaps": result.minor_gaps,
            "identifier_retry_count": 0 # Initialize or reset retry count
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Identifier Node failed: {str(e)}", exc_info=True)
        raise e
