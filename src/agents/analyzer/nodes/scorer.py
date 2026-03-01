import logging
import json

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....constants import NO_THREAD_ID
from ....ai_model_factory import get_model, MODEL_4O_MINI
from ....models.analysis import ScoringSchema, DeterministicScoringInput, ScoreBreakdown

logger = logging.getLogger(__name__)

def calculate_deterministic_score(input_data: DeterministicScoringInput) -> ScoringSchema:
    """
    Deterministically calculates the score based on the provided inputs.
    This is the source of truth for scoring logic.
    """
    # 1. Skills Match (30 pts)
    skills_score = max(0, min(30, input_data.skills_match_score))

    # 2. Experience Relevance (25 pts)
    exp_rel_score = max(0, min(25, input_data.experience_relevance_score))

    # 3. Seniority / Years of Experience (15 pts)
    seniority_score = max(0, min(15, input_data.seniority_score))

    # 4. Education & Certifications (10 pts)
    edu_score = max(0, min(10, input_data.education_certs_score))

    # 5. Keyword / ATS Coverage (10 pts)
    keyword_score = max(0, min(10, input_data.keyword_coverage_score))

    # 6. Accomplishments vs. Responsibilities (5 pts)
    acc_score = max(0, min(5, input_data.accomplishments_score))

    # 7. Formatting & Clarity (5 pts)
    format_score = max(0, min(5, input_data.formatting_clarity_score))

    # Total Score
    total_score = skills_score + exp_rel_score + seniority_score + edu_score + keyword_score + acc_score + format_score
    total_score = max(0, min(100, total_score))

    breakdown = ScoreBreakdown(
        skills_match=skills_score,
        experience_relevance=exp_rel_score,
        seniority=seniority_score,
        education_certs=edu_score,
        keyword_coverage=keyword_score,
        accomplishments=acc_score,
        formatting_clarity=format_score
    )

    reasoning = (
        f"Skills Match: {skills_score}/30\n"
        f"Experience Relevance: {exp_rel_score}/25\n"
        f"Seniority: {seniority_score}/15\n"
        f"Education & Certs: {edu_score}/10\n"
        f"Keyword Coverage: {keyword_score}/10\n"
        f"Accomplishments: {acc_score}/5\n"
        f"Formatting: {format_score}/5\n"
        f"Total Deterministic Score: {total_score}/100"
    )

    return ScoringSchema(score=total_score, breakdown=breakdown)

async def scorer_node(state: AnalyzerState, config: RunnableConfig = None):
    """Calculates a deterministic score based on identified matches and gaps."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Node started.")
    
    llm = get_model(model_name=MODEL_4O_MINI)
    
    # Define the tool for the LLM
    tools = [
        {
            "name": "calculate_deterministic_score",
            "description": "Calculates the final match score based on extracted numerical and categorical inputs from the analysis.",
            "parameters": DeterministicScoringInput.model_json_schema()
        }
    ]
    
    llm_with_tool = llm.bind_tools(tools, tool_choice="calculate_deterministic_score")
    
    major_hits = state.get("major_hits", [])
    minor_hits = state.get("minor_hits", [])
    major_gaps = state.get("major_gaps", [])
    minor_gaps = state.get("minor_gaps", [])
    candidate_location = state.get("candidate_location")
    candidate_notes = state.get("candidate_notes", [])
    candidate_metadata = state.get("candidate_metadata")
    
    candidate_info = f"Location: {candidate_location or 'Not specified'}\n"
    if candidate_metadata:
        candidate_info += "Metadata:\n"
        for key, value in candidate_metadata.items():
            if value:
                candidate_info += f"- {key}: {value}\n"
    if candidate_notes:
        candidate_info += "Notes:\n"
        for note in candidate_notes:
            content = note.get('content', '')
            candidate_info += f"- {content}\n"
    
    prompt = f"""You are a precise Scoring Analysis Agent for an ATS. Your objective is to extract the correct inputs for the deterministic scoring tool based on a qualitative analysis of hits and gaps.

    ### CANDIDATE INFO:
    {candidate_info}

    ### INPUT DATA:
    - **MAJOR HITS**: {major_hits}
    - **MINOR HITS**: {minor_hits}
    - **MAJOR GAPS**: {major_gaps}
    - **MINOR GAPS**: {minor_gaps}
    
    ### SCORING RUBRIC & CATEGORIES (FOR YOUR REFERENCE TO EXTRACT INPUTS):

    1. **Skills Match (30 pts)**:
       - 25–30: Covers nearly all required skills + most preferred.
       - 15–24: Covers most required, some preferred.
       - 5–14: Partial match, missing key skills.
       - 0–4: Minimal overlap.

    2. **Experience Relevance (25 pts)**:
       - 20–25: Direct experience in similar role/domain.
       - 12–19: Adjacent experience with transferable relevance.
       - 5–11: Some overlap but significant gaps.
       - 0–4: Largely unrelated background.

    3. **Seniority / Years of Experience (15 pts)**:
       - 12–15: Meets or slightly exceeds the requirement.
       - 8–11: Within 1–2 years of requirement.
       - 4–7: Noticeably under or significantly over (possible flight risk).
       - 0–3: Major mismatch.

    4. **Education & Certifications (10 pts)**:
       - 8–10: Degree field + level matches; relevant certs present.
       - 5–7: Degree present, minor field mismatch or certs missing.
       - 2–4: Degree field unrelated but experience compensates.
       - 0–1: No degree where required, no compensating factors.

    5. **Keyword / ATS Coverage (10 pts)**:
       - 8–10: High overlap in phrasing, titles, and terminology.
       - 5–7: Moderate overlap, some synonyms used.
       - 2–4: Low overlap, likely to fail ATS filters.
       - 0–1: Almost no matching language.

    6. **Accomplishments vs. Responsibilities (5 pts)**:
       - 4–5: Quantified achievements tied to relevant outcomes.
       - 2–3: Mix of achievements and duties.
       - 0–1: Purely duty-based, no measurable outcomes.

    7. **Formatting & Clarity (5 pts)**:
       - 4–5: Clean structure, no tables/graphics, easy to parse.
       - 2–3: Minor formatting issues.
       - 0–1: Heavy formatting, graphics, or parsing-hostile layout.

    ### TASK:
    1. Analyze the hits, gaps, and candidate info provided and call the `calculate_deterministic_score` tool with the appropriate arguments. 
    
    Ensure every deduction and point awarded is justified by the input data.
    """

    messages = [HumanMessage(content=prompt)]
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Node: starting LLM call (attempt {attempt + 1})...")
            response = await llm_with_tool.ainvoke(messages)
            logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Node: LLM call completed.")
            
            if not response.tool_calls:
                logger.warning(f"[ANALYZER_AGENT] [{clean_id_str}] No tool calls returned by LLM.")
                messages.append(AIMessage(content=response.content))
                messages.append(HumanMessage(content="Please call the `calculate_deterministic_score` tool with the appropriate arguments."))
                continue

            tool_call = response.tool_calls[0]
            tool_args = tool_call["args"]
            
            # Basic validation of tool_args could go here if needed
            # For now, we trust Pydantic and the LLM's adherence to the schema
            
            try:
                scoring_input = DeterministicScoringInput(**tool_args)
                result = calculate_deterministic_score(scoring_input)
                
                logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Node completed. Score: {result.score}")
                
                return {
                    "score": result.score,
                    "score_breakdown": result.breakdown.model_dump(),
                    "scorer_retry_count": 0, # Initialize or reset retry count
                    "metadata": {
                        **state.get("metadata", {}),
                        "status": "scored"
                    }
                }
            except Exception as e:
                logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Failed to parse tool arguments or calculate score: {str(e)}")
                messages.append(AIMessage(content="", tool_calls=response.tool_calls))
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=f"Error calculating score: {str(e)}. Please check your arguments and try again."
                ))
                continue

        except Exception as e:
            logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer attempt {attempt + 1} failed: {str(e)}", exc_info=True)
            if attempt == max_retries - 1:
                raise e

    raise RuntimeError(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Node failed after {max_retries} attempts.")
