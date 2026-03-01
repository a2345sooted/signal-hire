import logging
from fastapi import Request, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from src.api.errors import AppError
import traceback

logger = logging.getLogger(__name__)

def create_rfc7807_response(
    status_code: int,
    title: str,
    detail: str,
    error_code: str = None,
    instance: str = None,
    extra_details: dict = None
) -> JSONResponse:
    """Creates a JSONResponse following RFC 7807."""
    content = {
        "type": f"https://httpstatuses.com/{status_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if error_code:
        content["error_code"] = error_code
    if instance:
        content["instance"] = instance
    if extra_details:
        content["details"] = extra_details
        
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers={"Content-Type": "application/problem+json"}
    )

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return create_rfc7807_response(
        status_code=exc.status_code,
        title=exc.__class__.__name__,
        detail=exc.message,
        error_code=exc.error_code,
        instance=request.url.path,
        extra_details=exc.details
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return create_rfc7807_response(
        status_code=exc.status_code,
        title="HTTP Exception",
        detail=str(exc.detail),
        instance=request.url.path
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return create_rfc7807_response(
        status_code=422,
        title="Validation Error",
        detail="One or more fields failed validation",
        error_code="VALIDATION_ERROR",
        instance=request.url.path,
        extra_details={"errors": exc.errors()}
    )

async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled exception: {str(exc)}")
    
    # In production, we don't want to leak internal details
    # But for debugging purposes in this experimental project, 
    # we might want to see what happened.
    # Let's keep it safe for now.
    return create_rfc7807_response(
        status_code=500,
        title="Internal Server Error",
        detail="An unexpected error occurred. Please try again later.",
        error_code="INTERNAL_SERVER_ERROR",
        instance=request.url.path
    )

def register_exception_handlers(app: FastAPI):
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
