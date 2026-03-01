from typing import Any

# Global agent instances
_jd_agent = None
_resume_agent = None
_analyzer_agent = None
_optimizer_agent = None

def register_jd_agent(agent: Any):
    global _jd_agent
    _jd_agent = agent

def get_jd_agent():
    if _jd_agent is None:
        raise RuntimeError("JD Agent not compiled. Ensure compilation happens during startup.")
    return _jd_agent

def register_resume_agent(agent: Any):
    global _resume_agent
    _resume_agent = agent

def get_resume_agent():
    if _resume_agent is None:
        raise RuntimeError("Resume Agent not compiled. Ensure compilation happens during startup.")
    return _resume_agent

def register_analyzer_agent(agent: Any):
    global _analyzer_agent
    _analyzer_agent = agent

def get_analyzer_agent():
    if _analyzer_agent is None:
        raise RuntimeError("Analyzer Agent not compiled. Ensure compilation happens during startup.")
    return _analyzer_agent

def register_optimizer_agent(agent: Any):
    global _optimizer_agent
    _optimizer_agent = agent

def get_optimizer_agent():
    if _optimizer_agent is None:
        raise RuntimeError("Optimizer Agent not compiled. Ensure compilation happens during startup.")
    return _optimizer_agent
