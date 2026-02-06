import logging

from langgraph.graph import StateGraph, START, END

from ...agents.resume_processor.nodes.parser import parser_node
from ...agents.resume_processor.nodes.save_resume import save_resume_node
from ...agents.resume_processor.nodes.extractor import extractor_node
from ...agents.resume_processor.nodes.broadcast_started import broadcast_started_node
from ...agents.resume_processor.state import ResumeState

logger = logging.getLogger(__name__)

builder = StateGraph(ResumeState)

builder.add_node("broadcast_started", broadcast_started_node)
builder.add_node("extractor", extractor_node)
builder.add_node("parser", parser_node)
builder.add_node("save_resume", save_resume_node)

builder.add_edge(START, "broadcast_started")
builder.add_edge("broadcast_started", "extractor")
builder.add_edge("extractor", "parser")
builder.add_edge("parser", "save_resume")
builder.add_edge("save_resume", END)

def compile_resume_agent(checkpointer):
    """Compile the resume agent with a checkpointer."""
    return builder.compile(checkpointer=checkpointer)
