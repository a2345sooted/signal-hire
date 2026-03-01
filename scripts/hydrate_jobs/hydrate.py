import asyncio
import json
import logging
import os
import httpx
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

def get_access_token():
    """Reads access_token.txt and returns the token."""
    token_path = os.path.join(os.path.dirname(__file__), 'access_token.txt')
    try:
        with open(token_path, 'r') as f:
            token = f.read().strip()
            return token
    except FileNotFoundError:
        logger.error(f"Could not find {token_path}")
        return None

async def get_my_organizations(client: httpx.AsyncClient, token: str) -> List[Dict[str, Any]]:
    """Fetches user's organizations from the API."""
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(f"{BASE_URL}/organizations/mine", headers=headers)
    response.raise_for_status()
    return response.json()

async def create_job(client: httpx.AsyncClient, token: str, org_slug: str, job_data: Dict[str, Any]) -> str:
    """Creates a job via the API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Org-Slug": org_slug
    }
    # For the 'create' call as requested (part of initial workflow), we might pass minimal info
    # but the instruction says "calls create, calls patch with the meta, adds the jd"
    # Actually, the API create_job (src/api/jobs/create_job.py) takes JobCreate
    
    # We'll create it with just title and client_name first to follow the requested flow
    create_payload = {
        "title": job_data["title"],
        "client_name": job_data["client_name"]
    }
    
    response = await client.post(f"{BASE_URL}/jobs", headers=headers, json=create_payload)
    response.raise_for_status()
    return response.json()["job_id"]

async def patch_job(client: httpx.AsyncClient, token: str, org_slug: str, job_id: str, patch_data: Dict[str, Any]):
    """Patches a job via the API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Org-Slug": org_slug
    }
    response = await client.patch(f"{BASE_URL}/jobs/{job_id}", headers=headers, json=patch_data)
    response.raise_for_status()
    return response.json()

async def hydrate_jobs():
    token = get_access_token()
    if not token:
        logger.error("Failed to get access token. Exiting.")
        return

    # Load jobs from JSON
    json_path = os.path.join(os.path.dirname(__file__), 'jobs.json')
    try:
        with open(json_path, 'r') as f:
            jobs_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading {json_path}: {e}")
        return

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            orgs = await get_my_organizations(client, token)
            if not orgs:
                logger.error("No organizations found for the user.")
                return
            
            # Pick the first organization
            org = orgs[0]
            org_slug = org["slug"]
            logger.info(f"Using organization: {org['name']} ({org_slug})")
            
            for job_info in jobs_data:
                title = job_info.get("title")
                client_name = job_info.get("client_name")
                
                logger.info(f"Hydrating job: {title} for client: {client_name}")
                
                # 1. Create the job (initial creation with minimal info)
                job_id = await create_job(client, token, org_slug, job_info)
                logger.info(f"Created job with ID: {job_id}")
                
                # 2. Patch with metadata AND JD in a single call
                # This combines all updates into one request to avoid redundant agent triggers
                patch_payload = {k: v for k, v in job_info.items() if k not in ["title", "client_name"]}
                if patch_payload:
                    await patch_job(client, token, org_slug, job_id, patch_payload)
                    logger.info(f"Patched job {job_id} with metadata and JD. Backend should be processing it now.")

            logger.info("Hydration complete!")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(hydrate_jobs())
