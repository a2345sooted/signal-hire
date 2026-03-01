import logging
import json
from langchain_core.runnables import RunnableConfig
from ..state import OptimizerState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....ai_model_factory import get_model, MODEL_5_2

logger = logging.getLogger(__name__)

async def diff_generator_node(state: OptimizerState, config: RunnableConfig = None):
    """
    Creates an LLM-generated markdown diff between the original and optimized resume.
    """
    thread_id_str = get_thread_id(state, config)
    clean_id_str = strip_id_prefix(thread_id_str)
    
    logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Diff Generator Node started.")
    
    original_resume_data = state.get("resume_data", {})
    optimized_resume = state.get("optimized_resume")
    
    if not optimized_resume:
        logger.warning(f"[OPTIMIZER_AGENT] [{clean_id_str}] No optimized resume found in state. Skipping diff generation.")
        return {"diff_markdown": None}

    # Get original resume structured data or raw text
    original_structured = original_resume_data.get("structured_data", {})
    optimized_structured = optimized_resume.model_dump() if hasattr(optimized_resume, "model_dump") else optimized_resume
    
    llm = get_model(model_name=MODEL_5_2)
    
    prompt = f"""You are an expert Resume Editor. Your task is to generate a highly readable, professionally formatted Markdown document that explains PRECISELY what was changed during the resume optimization process.

CRITICAL: Do NOT use placeholder names like "Robert Schupp", "Tech Solutions Inc.", or generic "placeholder" text in your output. Use ONLY the data provided below.

ORIGINAL RESUME DATA (JSON):
{json.dumps(original_structured, indent=2)}

OPTIMIZED RESUME DATA (JSON):
{json.dumps(optimized_structured, indent=2)}

INSTRUCTIONS:
1.  **Format**: Use clean, well-structured, and spacious Markdown. 
2.  **Summary**: Start with a high-level summary of the overall optimization strategy used for this candidate. Wrap this summary in a blockquote or a separate section to distinguish it.
3.  **Section-by-Section Comparison**: 
    - Use clear, level 3 headers for each resume section (e.g., ### Professional Summary).
    - Use a horizontal rule (`---`) between major sections to improve scanability.
    - For each section, use a detailed bulleted list to describe specific changes.
    - Use bold text for labels and to highlight key improvements or added keywords.
    - Follow this EXACT format for each change:
      * **Changed from**: "[Original text segment...]" 
      * **Changed to**: "[Optimized text segment...]"
      * **Reason**: [Brief explanation of why this change improves ATS matching or role alignment].
    - Ensure there is an empty line between each bullet point to prevent the document from feeling cluttered.
4.  **Additions/Deletions**: Clearly label any entirely new sections or skills added (e.g., **[ADDED]**), and any information removed.
5.  **Spacing**: Use multiple line breaks between headers and lists. The output must be super easy to scan and read on a screen.
6.  **Style**: Professional, objective, and impact-oriented.

Generate the "Resume Optimization Diff" in Markdown format.
"""

    try:
        logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Invoking LLM for diff markdown. Prompt length: {len(prompt)}")
        response = await llm.ainvoke(prompt)
        diff_markdown = response.content if hasattr(response, "content") else str(response)
        
        logger.info(f"[OPTIMIZER_AGENT] [{clean_id_str}] Diff Generator Node completed. Response length: {len(diff_markdown)}")
        if "placeholder" in diff_markdown.lower() or "robert schupp" in diff_markdown.lower():
            logger.warning(f"[OPTIMIZER_AGENT] [{clean_id_str}] LLM generated placeholder/generic text!")
            logger.debug(f"[OPTIMIZER_AGENT] [{clean_id_str}] LLM response snippet: {diff_markdown[:500]}...")
        
        return {
            "diff_markdown": diff_markdown,
            "messages": state.get("messages", []) + ["LLM diff markdown generated."]
        }
    except Exception as e:
        logger.error(f"[OPTIMIZER_AGENT] [{clean_id_str}] Diff Generator Node failed: {str(e)}", exc_info=True)
        # Fallback to a simple message if LLM fails
        return {
            "diff_markdown": "### Resume Optimization Diff\n\n*Error generating detailed diff via LLM.*",
            "messages": state.get("messages", []) + [f"Failed to generate LLM diff: {str(e)}"]
        }
