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
    """Reads access_token from scripts/hydrate/access_token."""
    token_path = os.path.join(os.path.dirname(__file__), 'access_token')
    try:
        with open(token_path, 'r') as f:
            token = f.read().strip()
            return token
    except FileNotFoundError:
        logger.error(f"Could not find {token_path}")
        return None

async def get_my_organizations(client: httpx.AsyncClient, token: str) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(f"{BASE_URL}/organizations/mine", headers=headers)
    response.raise_for_status()
    return response.json()

async def create_candidate(client: httpx.AsyncClient, token: str, org_slug: str, candidate_data: Dict[str, Any]) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Org-Slug": org_slug
    }
    response = await client.post(f"{BASE_URL}/candidates", headers=headers, json=candidate_data)
    response.raise_for_status()
    return response.json()["candidate"]["id"]

async def upload_resume_file(client: httpx.AsyncClient, token: str, org_slug: str, candidate_id: str, file_path: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Org-Slug": org_slug
    }
    filename = os.path.basename(file_path)
    with open(file_path, 'rb') as f:
        docx_bytes = f.read()
    
    files = {
        "file": (filename, docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    }
    response = await client.post(f"{BASE_URL}/candidates/{candidate_id}/resumes/upload", headers=headers, files=files)
    response.raise_for_status()
    return response.json()

async def hydrate_candidates():
    token = get_access_token()
    if not token:
        return
    
    # Correct path to candidates directory relative to the script
    candidates_base_dir = os.path.join(os.path.dirname(__file__), 'candidates')
    if not os.path.exists(candidates_base_dir):
        logger.error(f"Candidates directory not found: {candidates_base_dir}")
        return

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            orgs = await get_my_organizations(client, token)
            if not orgs:
                logger.error("No organizations found.")
                return
            
            org_slug = orgs[0]["slug"]
            logger.info(f"Using organization: {orgs[0]['name']} ({org_slug})")
            
            # Iterate through candidate directories (1, 2, etc.)
            for entry in sorted(os.listdir(candidates_base_dir)):
                candidate_dir = os.path.join(candidates_base_dir, entry)
                if not os.path.isdir(candidate_dir):
                    continue
                
                logger.info(f"Processing candidate directory: {entry}")
                
                details_path = os.path.join(candidate_dir, 'details.json')
                if not os.path.exists(details_path):
                    logger.warning(f"No details.json found in {candidate_dir}")
                    continue
                
                with open(details_path, 'r') as f:
                    candidate_info = json.load(f)
                
                name = candidate_info.get("name")
                logger.info(f"Hydrating candidate: {name}")
                
                # 1. Create Candidate
                candidate_id = await create_candidate(client, token, org_slug, candidate_info)
                logger.info(f"Created candidate with ID: {candidate_id}")
                
                # 2. Upload Resume
                # Find the .docx file in the directory
                resume_file = None
                for f in os.listdir(candidate_dir):
                    if f.endswith('.docx'):
                        resume_file = os.path.join(candidate_dir, f)
                        break
                
                if resume_file:
                    logger.info(f"Uploading resume: {os.path.basename(resume_file)}")
                    await upload_resume_file(client, token, org_slug, candidate_id, resume_file)
                    logger.info(f"Uploaded resume for candidate {candidate_id}")
                else:
                    logger.warning(f"No .docx resume found for {name} in {candidate_dir}")

            logger.info("Candidate hydration complete!")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(hydrate_candidates())
