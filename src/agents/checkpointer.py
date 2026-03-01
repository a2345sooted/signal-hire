import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from src.config import settings

logger = logging.getLogger(__name__)

DATABASE_URL = settings.database_url_psycopg

# Global checkpointer instance and the pool
_pool: AsyncConnectionPool = None
_checkpointer: AsyncPostgresSaver = None

async def init_checkpointer():
    """
    Initialize the checkpointer using a connection pool.
    Call this during application startup (e.g., in FastAPI lifespan).
    """
    global _pool, _checkpointer
    
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=DATABASE_URL,
            max_size=50,
            kwargs={
                "autocommit": True, 
                "prepare_threshold": 0,
            },
            open=False,
            check=AsyncConnectionPool.check_connection,
        )
        await _pool.open()
        logger.info("Connection pool for LangGraph checkpointer opened (size: 50)")
    
    if _checkpointer is None:
        _checkpointer = AsyncPostgresSaver(conn=_pool)
        # Ensure tables are created and wait for them if needed
        await _checkpointer.setup()
        logger.info("LangGraph checkpointer initialized and tables verified/created")
    
    return _checkpointer

def get_checkpointer() -> AsyncPostgresSaver:
    """
    Get the initialized checkpointer instance.
    """
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized. Call init_checkpointer() during startup.")
    return _checkpointer

async def close_checkpointer():
    """
    Close the checkpointer pool during application shutdown.
    """
    global _pool, _checkpointer
    if _pool:
        await _pool.close()
        _pool = None
        _checkpointer = None
        logger.info("Checkpointer pool closed and reference cleared")
