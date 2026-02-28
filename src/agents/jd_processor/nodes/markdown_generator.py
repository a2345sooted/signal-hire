import logging

from langchain_core.runnables import RunnableConfig

from ....agents.jd_processor.state import JDState
from ....agents.utils import strip_id_prefix, get_thread_id
from ....constants import NO_THREAD_ID
from ....ai_model_factory import get_model, MODEL_4O_MINI

logger = logging.getLogger(__name__)

async def markdown_generator_node(state: JDState, config: RunnableConfig = None):
    thread_id_str = get_thread_id(state, config)
    
    # If it's the thread_id, it might have a prefix (e.g., jd_)
    clean_id_str = strip_id_prefix(thread_id_str)

    logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Markdown Generator Node started.")
    import time
    start_time = time.time()
    
    # Freeze input at node entry
    raw_text = state['raw_text']

    llm = get_model(model_name=MODEL_4O_MINI)
    
    prompt = f"""Convert the following job description into a well-formatted Markdown document with strategic highlighting.
Respond ONLY with the Markdown content.

HIGHLIGHTING RULES:
BE GENEROUS with highlighting. Use <mark> tags with ONLY these classes (DO NOT use bold/italics):
1. hl-yellow: Technical skills, tools, and technologies (e.g., Python, AWS, RAG, Distributed Systems).
2. hl-green: Key responsibilities, actions, and impact statements (e.g., "Lead the charge", "Architect", "Mentoring", "Collaborating").
3. hl-blue: Certifications, education, years of experience, or specific requirements (e.g., "10+ years", "Bachelor's degree").

FEW-SHOT EXAMPLE:
Input: Equifax is seeking a Principal Engineer to lead the charge. Requirements: Bachelor's degree and 7+ years experience. Deep knowledge of Python and AWS.
Output: Equifax is seeking a Principal Engineer to <mark class="hl-green">lead the charge</mark>.
- <mark class="hl-blue">Bachelor's degree</mark>
- <mark class="hl-blue">7+ years experience</mark>
- Deep knowledge of <mark class="hl-yellow">Python</mark> and <mark class="hl-yellow">AWS</mark>.

CRITICAL: 
- Start directly with content. 
- NO title/header. 
- NO bolding.
- Use ONLY header levels 1, 2, or 3 (i.e., #, ##, or ###). DO NOT use level 4 or lower.
- PRESERVE ALL ORIGINAL LINE BREAKS and structure from the input.

Job Description:
{raw_text}"""

    try:
        logger.debug(f"[JD_PROCESSOR] [{clean_id_str}] Markdown Generator LLM invocation started.")
        response = await llm.ainvoke(prompt)
        duration = time.time() - start_time
        logger.info(f"[JD_PROCESSOR] [{clean_id_str}] Markdown Generator LLM completed in {duration:.2f}s.")
        
        logger.debug(f"[JD_PROCESSOR] [{clean_id_str}] Generated Markdown (first 200 chars): {response.content[:200]}...")

        # Remove markdown entities (code blocks like ```markdown ... ```)
        content = response.content.strip()
        if content.startswith("```"):
            # Remove opening ```markdown or ```
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        return {
            "markdown": content
        }
    except Exception as e:
        logger.error(f"[JD_PROCESSOR] [{clean_id_str}] Markdown Generator Node failed: {str(e)}", exc_info=True)
        raise e
