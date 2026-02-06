import logging

from langgraph.graph import StateGraph, START, END

from ...agents.analyzer.nodes.identifier import identifier_node
from ...agents.analyzer.nodes.scorer import scorer_node
from ...agents.analyzer.nodes.save_analysis import save_analysis_node
from ...agents.analyzer.nodes.message import message_node
from ...agents.analyzer.state import AnalyzerState

logger = logging.getLogger(__name__)

builder = StateGraph(AnalyzerState)

# Add nodes
builder.add_node("identifier", identifier_node)
builder.add_node("scorer", scorer_node)
builder.add_node("save_analysis", save_analysis_node)
builder.add_node("message", message_node)

# Set up the flow
builder.add_edge(START, "identifier")
builder.add_edge("identifier", "scorer")
builder.add_edge("scorer", "message")
builder.add_edge("message", "save_analysis")
builder.add_edge("save_analysis", END)

def compile_analyzer_agent(checkpointer):
    """Compile the analyzer agent with a checkpointer."""
    return builder.compile(checkpointer=checkpointer)
