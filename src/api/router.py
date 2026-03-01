import logging
from fastapi import APIRouter
from src.api.jobs import (
    create_job, save_jd, get_jobs, upload_resume, get_resume,
    get_resume_analysis, get_analysis_status, get_resume_pdf, get_job, get_analysis,
    stop_resume_processing, delete_job, patch_job, add_job_note,
    patch_job_note, delete_job_note, attach_candidate, detach_candidate,
    optimize_resume, get_optimized_resume, generate_resume_diff, change_attachment_resume,
    re_analyze
)
from src.api.organizations import create_organization, get_my_organizations
from src.api.users import get_me
from src.api.candidates import (
    create_candidate, get_candidate, get_candidates, patch_candidate,
    add_candidate_note, get_candidate_notes, patch_candidate_note,
    delete_candidate_note, delete_candidate, upload_resume as upload_candidate_resume,
    get_resumes as get_candidate_resumes, delete_resume as delete_candidate_resume
)

logger = logging.getLogger(__name__)

router = APIRouter()

router.post("/v1/jobs", tags=["jobs"])(create_job)
router.post("/v1/jobs/save", tags=["jobs"])(save_jd)
router.get("/v1/jobs", tags=["jobs"])(get_jobs)
router.get("/v1/jobs/{job_id}", tags=["jobs"])(get_job)
router.patch("/v1/jobs/{job_id}", tags=["jobs"])(patch_job)
router.delete("/v1/jobs/{job_id}", tags=["jobs"])(delete_job)
router.post("/v1/jobs/{job_id}/notes", tags=["jobs"])(add_job_note)
router.patch("/v1/jobs/{job_id}/notes/{note_id}", tags=["jobs"])(patch_job_note)
router.delete("/v1/jobs/{job_id}/notes/{note_id}", tags=["jobs"])(delete_job_note)
router.post("/v1/jobs/{job_id}/candidates/{candidate_id}/attach", tags=["jobs"])(attach_candidate)
router.post("/v1/jobs/{job_id}/candidates/{candidate_id}/change-resume", tags=["jobs"])(change_attachment_resume)
router.post("/v1/jobs/{job_id}/candidates/{candidate_id}/optimize-resume", tags=["jobs"])(optimize_resume)
router.post("/v1/jobs/{job_id}/candidates/{candidate_id}/generate-resume-diff", tags=["jobs"])(generate_resume_diff)
router.get("/v1/jobs/{job_id}/candidates/{candidate_id}/optimized-resume", tags=["jobs"])(get_optimized_resume)
router.delete("/v1/jobs/{job_id}/candidates/{candidate_id}/detach", tags=["jobs"])(detach_candidate)
router.post("/v1/jobs/{job_id}/candidates/{candidate_id}/re-analyze", tags=["jobs"])(re_analyze)

router.post("/v1/organizations", tags=["organizations"])(create_organization)
router.get("/v1/organizations/mine", tags=["organizations"])(get_my_organizations)

router.post("/v1/candidates", tags=["candidates"])(create_candidate)
router.get("/v1/candidates", tags=["candidates"])(get_candidates)
router.get("/v1/candidates/{candidate_id}", tags=["candidates"])(get_candidate)
router.patch("/v1/candidates/{candidate_id}", tags=["candidates"])(patch_candidate)
router.delete("/v1/candidates/{candidate_id}", tags=["candidates"])(delete_candidate)
router.post("/v1/candidates/{candidate_id}/notes", tags=["candidates"])(add_candidate_note)
router.get("/v1/candidates/{candidate_id}/notes", tags=["candidates"])(get_candidate_notes)
router.patch("/v1/candidates/{candidate_id}/notes/{note_id}", tags=["candidates"])(patch_candidate_note)
router.delete("/v1/candidates/{candidate_id}/notes/{note_id}", tags=["candidates"])(delete_candidate_note)
router.post("/v1/candidates/{candidate_id}/resumes/upload", tags=["candidates"])(upload_candidate_resume)
router.get("/v1/candidates/{candidate_id}/resumes", tags=["candidates"])(get_candidate_resumes)
router.delete("/v1/candidates/{candidate_id}/resumes/{resume_id}", tags=["candidates"])(delete_candidate_resume)

router.get("/v1/users/me", tags=["users"])(get_me)

router.post("/v1/resumes/upload", tags=["resumes"])(upload_resume)
router.post("/v1/resumes/stop/{job_id}", tags=["resumes"])(stop_resume_processing)
router.get("/v1/resumes/{resume_id}", tags=["resumes"])(get_resume)
router.get("/v1/resumes/{resume_id}/pdf", tags=["resumes"])(get_resume_pdf)
router.get("/v1/resume/{resume_id}/analysis", tags=["resumes"])(get_resume_analysis)
router.get("/v1/jobs/{job_id}/candidates/{candidate_id}/analysis", tags=["analyses"])(get_analysis)
router.get("/v1/jobs/{job_id}/candidates/{candidate_id}/analysis/status", tags=["analyses"])(get_analysis_status)
