import logging

from langgraph.graph import StateGraph, START, END

from ...agents.analyzer.nodes.identifier import identifier_node
from ...agents.analyzer.nodes.identifier_checker import identifier_checker_node
from ...agents.analyzer.nodes.identifier_repairer import identifier_repairer_node
from ...agents.analyzer.nodes.scorer import scorer_node
from ...agents.analyzer.nodes.scorer_checker import scorer_checker_node
from ...agents.analyzer.nodes.scorer_repairer import scorer_repairer_node
from ...agents.analyzer.nodes.message_checker import message_checker_node
from ...agents.analyzer.nodes.message_repairer import message_repairer_node
from ...agents.analyzer.nodes.hiring_notes import hiring_notes_node
from ...agents.analyzer.nodes.save_analysis import save_analysis_node
from ...agents.analyzer.nodes.message import message_node
from ...agents.analyzer.state import AnalyzerState

logger = logging.getLogger(__name__)

builder = StateGraph(AnalyzerState)

# Add nodes
builder.add_node("identifier", identifier_node)
builder.add_node("identifier_checker", identifier_checker_node)
builder.add_node("identifier_repairer", identifier_repairer_node)
builder.add_node("scorer", scorer_node)
builder.add_node("scorer_checker", scorer_checker_node)
builder.add_node("scorer_repairer", scorer_repairer_node)
builder.add_node("message_checker", message_checker_node)
builder.add_node("message_repairer", message_repairer_node)
builder.add_node("hiring_notes", hiring_notes_node)
builder.add_node("save_analysis", save_analysis_node)
builder.add_node("message", message_node)

def should_retry_identification(state: AnalyzerState):
    """Router to decide if we should retry identification or move on."""
    feedback = state.get("identifier_feedback")
    retry_count = state.get("identifier_retry_count", 0)
    
    if feedback and retry_count < 3:
        return "retry"
    return "continue"

def should_retry_scoring(state: AnalyzerState):
    """Router to decide if we should retry scoring or move on."""
    feedback = state.get("scorer_feedback")
    retry_count = state.get("scorer_retry_count", 0)
    
    if feedback and retry_count < 3:
        return "retry"
    return "continue"
    
def should_retry_message(state: AnalyzerState):
    """Router to decide if we should retry message generation or move on."""
    feedback = state.get("message_feedback")
    retry_count = state.get("message_retry_count", 0)
    
    if feedback and retry_count < 3:
        return "retry"
    return "continue"

# Set up the flow
builder.add_edge(START, "identifier")
builder.add_edge("identifier", "identifier_checker")

builder.add_conditional_edges(
    "identifier_checker",
    should_retry_identification,
    {
        "retry": "identifier_repairer",
        "continue": "scorer"
    }
)

builder.add_edge("identifier_repairer", "identifier_checker")
builder.add_edge("scorer", "scorer_checker")

builder.add_conditional_edges(
    "scorer_checker",
    should_retry_scoring,
    {
        "retry": "scorer_repairer",
        "continue": "message"
    }
)

builder.add_edge("scorer_repairer", "scorer_checker")
builder.add_edge("message", "message_checker")

builder.add_conditional_edges(
    "message_checker",
    should_retry_message,
    {
        "retry": "message_repairer",
        "continue": "hiring_notes"
    }
)

builder.add_edge("message_repairer", "message_checker")
builder.add_edge("hiring_notes", "save_analysis")
builder.add_edge("save_analysis", END)

def compile_analyzer_agent(checkpointer):
    """Compile the analyzer agent with a checkpointer."""
    return builder.compile(checkpointer=checkpointer)
