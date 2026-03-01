import logging
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.analysis import DeterministicScoringInput
from .scorer import calculate_deterministic_score

logger = logging.getLogger(__name__)

async def scorer_repairer_node(state: AnalyzerState, config: RunnableConfig = None):
    """Repairs the score based on feedback from the checker."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Repairer Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    
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
    score = state.get("score")
    score_breakdown = state.get("score_breakdown")
    feedback = state.get("scorer_feedback")
    
    prompt = f"""You are a precise Scoring Analysis Agent for an ATS. Your objective is to REVISE the match score based on critical feedback from an auditor.

    ### INPUT DATA:
    - **MAJOR HITS**: {major_hits}
    - **MINOR HITS**: {minor_hits}
    - **MAJOR GAPS**: {major_gaps}
    - **MINOR GAPS**: {minor_gaps}
    
    ### PREVIOUS ATTEMPT:
    - **TOTAL SCORE**: {score}/100
    - **BREAKDOWN**: {score_breakdown}

    ### CRITICAL FEEDBACK FROM AUDITOR:
    {feedback}

    ### SCORING RUBRIC & CATEGORIES (FOR YOUR REFERENCE):
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
       - 4–7: Noticeably under or significantly over.
       - 0–3: Major mismatch.

    4. **Education & Certifications (10 pts)**:
       - 8–10: Degree field + level matches; relevant certs present.
       - 5–7: Degree present, minor field mismatch or certs missing.
       - 2–4: Degree field unrelated but experience compensates.
       - 0–1: No degree where required.

    5. **Keyword / ATS Coverage (10 pts)**:
       - 8–10: High overlap in phrasing, titles, and terminology.
       - 5–7: Moderate overlap.
       - 2–4: Low overlap.
       - 0–1: Almost no matching language.

    6. **Accomplishments vs. Responsibilities (5 pts)**:
       - 4–5: Quantified achievements tied to relevant outcomes.
       - 2–3: Mix of achievements and duties.
       - 0–1: Purely duty-based.

    7. **Formatting & Clarity (5 pts)**:
       - 4–5: Clean structure.
       - 2–3: Minor formatting issues.
       - 0–1: Heavy formatting.

    ### TASK:
    Carefully review the feedback and recalculate the score inputs. 
    You MUST address the specific points raised by the auditor. 
    Justify your new scores in your reasoning, ensuring they align with BOTH the feedback and the rubric categories. 
    Call the `calculate_deterministic_score` tool with the appropriate revised arguments.
    """

    messages = [HumanMessage(content=prompt)]
    try:
        response = await llm_with_tool.ainvoke(messages)
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_args = tool_call["args"]
            scoring_input = DeterministicScoringInput(**tool_args)
            result = calculate_deterministic_score(scoring_input)
            
            logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Repairer Node completed. New Score: {result.score}")
            
            return {
                "score": result.score,
                "score_breakdown": result.breakdown.model_dump(),
                "scorer_feedback": None # Clear feedback after repair
            }
        else:
             logger.warning(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Repairer Node failed to produce tool call.")
             return {}
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Repairer Node failed: {str(e)}", exc_info=True)
        return {}
