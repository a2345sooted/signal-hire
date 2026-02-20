import logging
from fastapi import APIRouter
from src.api.job_handler import save_jd, get_jobs, upload_resume, get_resume, get_resume_analysis, get_resume_pdf, get_job, get_analysis, stop_resume_processing, delete_job_endpoint
from src.api.organization_handler import create_organization, get_my_organizations
from src.api.user_handler import get_me, accept_terms
from src.api.ws.router import router as ws_router

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok"}

router.post("/v1/jobs/save", tags=["jobs"])(save_jd)
router.get("/v1/jobs", tags=["jobs"])(get_jobs)
router.get("/v1/jobs/{job_id}", tags=["jobs"])(get_job)
router.delete("/v1/jobs/{job_id}", tags=["jobs"])(delete_job_endpoint)

router.post("/v1/organizations", tags=["organizations"])(create_organization)
router.get("/v1/organizations/mine", tags=["organizations"])(get_my_organizations)

router.get("/v1/users/me", tags=["users"])(get_me)
router.post("/v1/users/accept-terms", tags=["users"])(accept_terms)

router.post("/v1/resumes/upload", tags=["resumes"])(upload_resume)
router.post("/v1/resumes/stop/{job_id}", tags=["resumes"])(stop_resume_processing)
router.get("/v1/resumes/{resume_id}", tags=["resumes"])(get_resume)
router.get("/v1/resumes/{resume_id}/pdf", tags=["resumes"])(get_resume_pdf)
router.get("/v1/resume/{resume_id}/analysis", tags=["resumes"])(get_resume_analysis)
router.get("/v1/analysis/{analysis_id}", tags=["analyses"])(get_analysis)

router.include_router(ws_router, prefix="/v1/ws", tags=["websocket"])
