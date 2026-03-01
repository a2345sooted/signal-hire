import logging

from langgraph.graph import StateGraph, START, END

from ...agents.jd_processor.nodes.markdown_generator import markdown_generator_node
from ...agents.jd_processor.nodes.structured_data import structured_data_node
from ...agents.jd_processor.nodes.extract_details import extract_details_node
from ...agents.jd_processor.nodes.validate_and_save import validate_and_save_node
from ...agents.jd_processor.state import JDState

logger = logging.getLogger(__name__)

builder = StateGraph(JDState)

builder.add_node("structured_data", structured_data_node)
builder.add_node("markdown_generator", markdown_generator_node)
builder.add_node("extract_details", extract_details_node)
builder.add_node("validate_and_save", validate_and_save_node)

builder.add_edge(START, "structured_data")
builder.add_edge(START, "markdown_generator")
builder.add_edge(START, "extract_details")

# Parallel tracks converge at validate_and_save
builder.add_edge("structured_data", "validate_and_save")
builder.add_edge("markdown_generator", "validate_and_save")
builder.add_edge("extract_details", "validate_and_save")

# Finalization: validate_and_save -> END

# Sequential execution: validate_and_save -> END
builder.add_edge("validate_and_save", END)

def compile_jd_agent(checkpointer):
    """Compile the JD agent with a checkpointer."""
    return builder.compile(checkpointer=checkpointer)
