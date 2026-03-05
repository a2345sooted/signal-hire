import logging
import os
from typing import Optional

from fastapi import Request, HTTPException
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, JSONResponse

from src.database import AsyncSessionLocal
from src.models.db_models import Organization, User, OrganizationUser, OrgRole
from src.api.middleware.auth0 import auth0_verifier, auth0_management
from src.api.errors import AuthenticationError

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip health checks
        if request.url.path in ["/health", "/api/health"]:
            return await call_next(request)

        # Skip public invite details endpoint (GET)
        # /api/v1/invites/{invite_id}
        import re
        if re.search(r"/v1/invites/[0-9a-fA-F-]+$", request.url.path) and request.method == "GET":
            return await call_next(request)

        # Skip paths that don't start with /api (FastAPI handles 404 for these, but middleware runs first)
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        # Get Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return await self._error_response(401, "Missing or invalid Authorization header")

        token = auth_header.split(" ")[1]
        
        try:
            payload = await auth0_verifier.verify(token)
            sub = payload.get("sub")
            
            if not sub:
                return await self._error_response(401, "Invalid token: missing sub claim")

            async with AsyncSessionLocal() as session:
                # 1. Get or create user
                result = await session.execute(select(User).where(User.sub == sub))
                user = result.scalar_one_or_none()

                if not user:
                    # If user is not in our DB, try to get real email from Auth0 Management API
                    email = payload.get("email")
                    if not email:
                        logger.info(f"Email not in token for {sub}, fetching from Auth0 Management API...")
                        profile = await auth0_management.get_user_profile(sub)
                        email = profile.get("email")
                    
                    if not email:
                        email = f"{sub}@placeholder.com"
                        logger.warning(f"Could not find email for {sub}, using placeholder: {email}")

                    user = User(sub=sub, email=email)
                    session.add(user)
                    await session.flush()
                    logger.info(f"Created new user from Auth0: {email} ({sub})")
                else:
                    email = user.email # Use existing email

                await session.commit()

                # Set the IDs in request state
                request.state.user_id = user.id
                
                # Check for organizations only to set org_id if they belong to one
                # Note: A user can belong to multiple organizations.
                # If they do, we'll need a better way to handle the 'current' organization.
                # For now, we'll just pick the first one to avoid crashes.
                result = await session.execute(
                    select(OrganizationUser)
                    .where(OrganizationUser.user_id == user.id)
                    .limit(1)
                )
                org_user = result.scalar_one_or_none()
                
                if org_user:
                    request.state.org_id = org_user.org_id
                    request.state.osuser_id = org_user.id
                    logger.debug(f"Auth set: org_id={org_user.org_id}, user_id={user.id}, osuser_id={org_user.id}")
                else:
                    request.state.org_id = None
                    request.state.osuser_id = None
                    logger.debug(f"Auth set: user_id={user.id} (no organization)")

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return await self._error_response(401, f"Authentication failed: {str(e)}")

        return await call_next(request)

    async def _error_response(self, status_code: int, detail: str) -> JSONResponse:
        from src.api.exception_handlers import create_rfc7807_response
        return create_rfc7807_response(
            status_code=status_code,
            title="Authentication Error",
            detail=detail,
            error_code="AUTHENTICATION_FAILED"
        )
