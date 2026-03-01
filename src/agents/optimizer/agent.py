import logging
from langgraph.graph import StateGraph, START, END
from ...agents.optimizer.nodes.planner import planner_node
from ...agents.optimizer.nodes.optimizer import optimizer_node
from ...agents.optimizer.nodes.save_optimized_resume import save_optimized_resume_node
from ...agents.optimizer.state import OptimizerState

logger = logging.getLogger(__name__)

builder = StateGraph(OptimizerState)

# Add nodes
builder.add_node("planner", planner_node)
builder.add_node("optimizer", optimizer_node)
builder.add_node("save_optimized_resume", save_optimized_resume_node)

# Set up the flow
builder.add_edge(START, "planner")
builder.add_edge("planner", "optimizer")
builder.add_edge("optimizer", "save_optimized_resume")
builder.add_edge("save_optimized_resume", END)

def compile_optimizer_agent(checkpointer):
    """Compile the optimizer agent with a checkpointer."""
    return builder.compile(checkpointer=checkpointer)
