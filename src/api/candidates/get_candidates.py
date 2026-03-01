import logging
from typing import Annotated, Optional
from fastapi import Depends, Request, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.repositories.candidate_repository import CandidateRepository
from src.repositories.organization_repository import OrganizationRepository

from src.api.candidates.models import CandidateListBrief

logger = logging.getLogger(__name__)

async def get_candidates(
    request: Request,
    x_org_slug: Annotated[str, Header()],
    db: AsyncSession = Depends(get_db),
    q: Optional[str] = Query(None),
    has_resume: Optional[bool] = Query(None),
    no_roles: Optional[bool] = Query(None)
):
    """
    Get all candidates for an organization with filtering.
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Resolve organization by slug
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_organization_by_slug(x_org_slug)
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization '{x_org_slug}' not found")

    # Check access
    role = await org_repo.get_user_role_in_org(user_id, org.id)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have access to this organization")

    logger.info(f"Fetching candidates for org: {org.name} ({org.id}) with filters: q={q}, "
                f"has_resume={has_resume}, no_roles={no_roles}")

    candidate_repo = CandidateRepository(db)
    candidates_data = await candidate_repo.get_candidates(
        org_id=org.id,
        search_query=q,
        has_resume=has_resume,
        no_roles=no_roles
    )

    # Validate with Pydantic model
    candidates = [CandidateListBrief.model_validate(c) for c in candidates_data]

    return {
        "success": True,
        "candidates": candidates
    }
