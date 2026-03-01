from typing import Optional, Dict, Any
from fastapi import HTTPException

class AppError(Exception):
    """Base class for application errors."""
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details
        super().__init__(message)

class ResourceNotFoundError(AppError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=404, error_code="RESOURCE_NOT_FOUND", details=details)

class AuthenticationError(AppError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=401, error_code="AUTHENTICATION_FAILED", details=details)

class AuthorizationError(AppError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=403, error_code="AUTHORIZATION_FAILED", details=details)

class ValidationError(AppError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=400, error_code="VALIDATION_FAILED", details=details)

class ConflictError(AppError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=409, error_code="CONFLICT", details=details)
