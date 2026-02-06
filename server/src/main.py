import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.router import router
from .api.ui_routes import router as ui_router
from .database import engine
from .logging_config import setup_logging
from .agents.checkpointer import init_checkpointer, close_checkpointer

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(fast_app: FastAPI):
    logger.info("Starting up signal-hire-service...")
    
    # 1. Initialize checkpointer
    checkpointer = await init_checkpointer()
    
    # 2. Compile and register agents
    from .agents.jd_processor.agent import compile_jd_agent
    from .agents.resume_processor.agent import compile_resume_agent
    from .agents.analyzer.agent import compile_analyzer_agent
    from .agents.registry import (
        register_jd_agent, 
        register_resume_agent, 
        register_analyzer_agent
    )
    
    jd_agent = compile_jd_agent(checkpointer)
    resume_agent = compile_resume_agent(checkpointer)
    analyzer_agent = compile_analyzer_agent(checkpointer)
    
    register_jd_agent(jd_agent)
    register_resume_agent(resume_agent)
    register_analyzer_agent(analyzer_agent)
    
    logger.info("Agents compiled and registered with persistent checkpointer.")
    
    yield
    
    logger.info("Shutting down signal-hire-service...")
    # Shutdown: Close database connections
    await engine.dispose()
    await close_checkpointer()

app = FastAPI(lifespan=lifespan)

app.include_router(router, prefix="/api")
app.include_router(ui_router, tags=["ui"])
