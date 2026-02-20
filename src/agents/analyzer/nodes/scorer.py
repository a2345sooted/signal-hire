import logging
import json

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage

from ....agents.analyzer.state import AnalyzerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....constants import NO_THREAD_ID
from ....ai_model_factory import get_model, MODEL_5_2
from ....models.analysis import ScoringSchema, DeterministicScoringInput, ScoreBreakdown

logger = logging.getLogger(__name__)

def calculate_deterministic_score(input_data: DeterministicScoringInput) -> ScoringSchema:
    """
    Deterministically calculates the score based on the provided inputs.
    This is the source of truth for scoring logic.
    """
    # 1. Critical Requirements (Max 40)
    critical_score = input_data.critical_hits_count * 10 # Example: 10 pts per major hit, capped at 40
    for penalty in input_data.major_gap_penalties:
        critical_score -= penalty
    for penalty in input_data.specific_penalties:
        critical_score -= penalty
    critical_score = max(0, min(40, critical_score))

    # 2. Important Requirements (Max 25)
    important_score = (input_data.important_hits_count * 3) # 3 pts per minor hit
    important_score += (input_data.partial_skill_hits_count * 1.5) # 50% value
    important_score += (input_data.learning_skill_hits_count * 0.6) # 20% value
    for penalty in input_data.minor_gap_penalties:
        important_score -= penalty
    if input_data.has_85_percent_important:
        important_score += 2
    important_score = max(0, min(25, int(important_score)))

    # 3. Nice-to-Have (Max 10)
    nice_to_have_score = max(0, min(10, input_data.nice_to_have_hits_count))

    # 4. Experience Level Match (Max 15)
    exp_base = input_data.experience_years_match_score
    exp_score = exp_base * input_data.experience_multiplier
    exp_score += input_data.experience_bonus_penalty
    
    # Special Modifier: NO compensatory points for Experience if Critical Requirements are missed (< 30)
    if critical_score < 30:
        exp_score = 0
    
    exp_score = max(0, min(15, int(exp_score)))

    # 5. Presentation & Relevance (Max 10)
    pres_score = input_data.presentation_quality_score + input_data.tailoring_score + input_data.presentation_bonus_penalty
    pres_score = max(0, min(10, pres_score))

    # Total Score
    total_score = critical_score + important_score + nice_to_have_score + exp_score + pres_score
    total_score = max(0, min(100, total_score))

    breakdown = ScoreBreakdown(
        critical_requirements=critical_score,
        important_requirements=important_score,
        nice_to_have=nice_to_have_score,
        experience_level=exp_score,
        presentation=pres_score
    )

    reasoning = (
        f"Critical: {critical_score}/40 (Hits: {input_data.critical_hits_count}, Penalties: {sum(input_data.major_gap_penalties) + sum(input_data.specific_penalties)})\n"
        f"Important: {important_score}/25 (Hits: {input_data.important_hits_count}, Partial: {input_data.partial_skill_hits_count}, Learning: {input_data.learning_skill_hits_count}, Gaps: {sum(input_data.minor_gap_penalties)}, Bonus: {input_data.has_85_percent_important})\n"
        f"Nice-to-Have: {nice_to_have_score}/10\n"
        f"Experience: {exp_score}/15 (Base: {exp_base}, Mult: {input_data.experience_multiplier}, Bonus/Penalty: {input_data.experience_bonus_penalty})\n"
        f"Presentation: {pres_score}/10 (Quality: {input_data.presentation_quality_score}, Tailoring: {input_data.tailoring_score}, Bonus/Penalty: {input_data.presentation_bonus_penalty})\n"
        f"Total Deterministic Score: {total_score}/100"
    )

    return ScoringSchema(score=total_score, breakdown=breakdown, reasoning=reasoning)

async def scorer_node(state: AnalyzerState, config: RunnableConfig = None):
    """Calculates a deterministic score based on identified matches and gaps."""
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer Node started.")
    
    llm = get_model(model_name=MODEL_5_2)
    
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
    
    prompt = f"""You are a precise Scoring Analysis Agent for an ATS. Your objective is to extract the correct inputs for the deterministic scoring tool based on a qualitative analysis of hits and gaps.

    ### INPUT DATA:
    - **MAJOR HITS**: {major_hits}
    - **MINOR HITS**: {minor_hits}
    - **MAJOR GAPS**: {major_gaps}
    - **MINOR GAPS**: {minor_gaps}
    
    ### SCORING RUBRIC & CATEGORIES (FOR YOUR REFERENCE TO EXTRACT INPUTS):

    1. **Critical Requirements (Max 40 pts)**:
       - **Hits**: Award 10 points per major hit against critical JD requirements.
       - **Gaps**: Deduct 10-15 points per major gap (very strict). 
       - **Specific Penalties**: -20 for missing a must-have certification/degree; -15 for a missing core technical skill; -12 for missing years of experience threshold.
       - **Floor/Cap**: Min 0, Max 40.

    2. **Important Requirements (Max 25 pts)**:
       - **Hits**: Award 3 points per minor hit. Award 1.5 points for related/transferable skills. Award 0.6 points if they show they are learning the skill.
       - **Gaps**: Deduct 5-8 points per minor gap.
       - **Bonus**: +2 if they have 85%+ of important requirements.
       - **Floor/Cap**: Min 0, Max 25.

    3. **Nice-to-Have (Max 10 pts)**:
       - **Hits**: Award 1 point for each nice-to-have hit.
       - **Floor/Cap**: Min 0, Max 10.

    4. **Experience Level Match (Max 15 pts)**:
       - **Years**: Meets (100-120%): 10-12 pts; Slightly under (75-99%): 5-7 pts; Significantly under: 0-2 pts; Overqualified (150%+): 8-10 pts.
       - **Multiplier**: Directly relevant (1.0x), Adjacent (0.6x), Transferable (0.4x).
       - **Bonus/Penalty**: Upward trajectory (+1), Job hopping (-3), Career pivot (0).

    5. **Presentation & Relevance (Max 10 pts)**:
       - **Quality**: Well-organized (4), Acceptable (2), Poor (0).
       - **Tailoring**: Clearly tailored (4), Generic (1), Spray-and-pray (0).
       - **Bonus/Penalty**: Quantified achievements (+1), Typos (-3), Unexplained gaps > 1yr (-3).

    ### TASK:
    Analyze the hits and gaps provided and call the `calculate_deterministic_score` tool with the appropriate arguments. 
    Ensure every deduction and point awarded is justified by the input data.
    """

    messages = [HumanMessage(content=prompt)]
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Broadcast status
            from ....api.ws.manager import manager
            import json
            job_id = state.get("job_id")
            resume_id = state.get("resume_id")
            if job_id:
                await manager.broadcast_to_job(
                    json.dumps({
                        "status": "Scoring",
                        "message": "Calculating resume-job match score...",
                        "resume_id": str(resume_id),
                        "completed": False
                    }),
                    str(job_id)
                )

            logger.info(f"[ANALYZER_AGENT] [{clean_id_str}] Scorer attempt {attempt + 1}")
            response = await llm_with_tool.ainvoke(messages)
            
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
                    "scoring_reasoning": result.reasoning,
                    "messages": state.get("messages", []) + [f"Analysis complete. Score: {result.score}%"],
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
