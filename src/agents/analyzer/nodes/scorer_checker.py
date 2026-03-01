import logging
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2

logger = logging.getLogger(__name__)

class ScorerCheckResult(BaseModel):
    is_reasonable: bool = Field(..., description="Whether the score is reasonable given the hits and gaps.")
    feedback: str = Field(..., description="Detailed feedback if the score is not reasonable.")

async def scorer_checker_node(state: AnalyzerState, config: RunnableConfig = None):
    """Checks if the score is reasonable against the rubric and hits/gaps."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Checker Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    structured_checker = llm.with_structured_output(ScorerCheckResult)
    
    major_hits = state.get("major_hits", [])
    minor_hits = state.get("minor_hits", [])
    major_gaps = state.get("major_gaps", [])
    minor_gaps = state.get("minor_gaps", [])
    score = state.get("score")
    score_breakdown = state.get("score_breakdown")
    
    prompt = f"""You are a senior ATS Auditor. Your job is to verify if the scoring provided by another agent is reasonable and consistent with the rubric.

    ### INPUT DATA:
    - **MAJOR HITS**: {major_hits}
    - **MINOR HITS**: {minor_hits}
    - **MAJOR GAPS**: {major_gaps}
    - **MINOR GAPS**: {minor_gaps}
    
    ### CURRENT SCORE:
    - **TOTAL SCORE**: {score}/100
    - **BREAKDOWN**: {score_breakdown}

    ### SCORING RUBRIC & CATEGORIES:
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
    Evaluate if the current score and its breakdown are reasonable based on the hits and gaps.

    **Guidelines for Reasonableness**:
    - **Accept Tolerance**: Minor differences of opinion (e.g., 1-3 points) within a range are normal and should NOT trigger a retry.
    - **Logical Consistency**: Focus on major misalignments. For example, if there are "MAJOR GAPS" in skills, the "Skills Match" score should not be 25+.
    - **Rubric Adherence**: Ensure the score reflects the categorical descriptions in the rubric.
    - **Constructive Only**: Only mark as `is_reasonable=False` if there is a clear, significant error that would mislead a recruiter.

    If you find such inconsistencies, mark it as NOT reasonable and provide specific, constructive feedback on which category needs adjustment and why.
    """

    try:
        result = await structured_checker.ainvoke(prompt)
        logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Checker: is_reasonable={result.is_reasonable}")
        
        return {
            "scorer_feedback": result.feedback if not result.is_reasonable else None,
            "scorer_retry_count": state.get("scorer_retry_count", 0) + (0 if result.is_reasonable else 1)
        }
    except Exception as e:
        logger.error(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Checker failed: {str(e)}", exc_info=True)
        # On failure, we might want to proceed or retry the check itself.
        # Proceeding as reasonable for now to avoid blocking.
        return {"scorer_feedback": None}
