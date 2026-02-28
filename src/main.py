import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.router import router
from src.api.middleware.auth import AuthMiddleware
from src.database import engine
from src.config import settings
from src.logging_config import setup_logging
from src.agents.checkpointer import init_checkpointer, close_checkpointer

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(fast_app: FastAPI):
    logger.info("Starting up signal-hire-service with validated configuration...")
    # Config is already validated by Pydantic Settings on import in src.config
    
    # 1. Initialize checkpointer
    checkpointer = await init_checkpointer()
    
    # 2. Compile and register agents
    from src.agents.jd_processor.agent import compile_jd_agent
    from src.agents.resume_processor.agent import compile_resume_agent
    from src.agents.analyzer.agent import compile_analyzer_agent
    from src.agents.registry import (
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

@app.get("/health")
async def health():
    return {"status": "ok"}

app.add_middleware(AuthMiddleware)

app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
