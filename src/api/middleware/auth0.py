import logging
from typing import Any, Dict, Optional

import httpx
from jose import jwt
from src.config import settings

logger = logging.getLogger(__name__)

AUTH0_DOMAIN = settings.auth0_domain
AUTH0_AUDIENCE = settings.auth0_audience
AUTH0_CLIENT_ID = settings.auth0_client_id
AUTH0_CLIENT_SECRET = settings.auth0_client_secret

ALGORITHMS = ["RS256"]

class Auth0Verifier:
    def __init__(self):
        self.jwks: Optional[Dict[str, Any]] = None

    async def _fetch_jwks(self) -> Dict[str, Any]:
        if self.jwks:
            return self.jwks

        url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            self.jwks = response.json()
            return self.jwks

    async def verify(self, token: str) -> Dict[str, Any]:
        if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
            # Fallback for local development if env vars are missing
            # In a real production app, this should probably raise an error
            logger.warning("AUTH0_DOMAIN or AUTH0_AUDIENCE not set. Skipping verification (NOT SECURE).")
            return jwt.get_unverified_claims(token)

        try:
            jwks = await self._fetch_jwks()
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
            
            if rsa_key:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=ALGORITHMS,
                    audience=AUTH0_AUDIENCE,
                    issuer=f"https://{AUTH0_DOMAIN}/"
                )
                return payload
            
            raise Exception("Unable to find appropriate key")
        except Exception as e:
            logger.error(f"JWT verification failed: {e}")
            raise

class Auth0ManagementClient:
    def __init__(self):
        self.domain = AUTH0_DOMAIN
        self.client_id = AUTH0_CLIENT_ID
        self.client_secret = AUTH0_CLIENT_SECRET
        self.access_token: Optional[str] = None

    async def _get_access_token(self) -> str:
        if self.access_token:
            # We could implement token expiry check here, but for simplicity we'll just fetch a new one if it fails or use it as is
            return self.access_token

        if not self.domain or not self.client_id or not self.client_secret:
            logger.warning("Auth0 Management API credentials missing.")
            return ""

        url = f"https://{self.domain}/oauth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": f"https://{self.domain}/api/v2/",
            "grant_type": "client_credentials"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            return self.access_token

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        token = await self._get_access_token()
        if not token:
            return {}

        url = f"https://{self.domain}/api/v2/users/{user_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Failed to fetch user profile from Auth0: {response.text}")
                return {}
            return response.json()

auth0_verifier = Auth0Verifier()
auth0_management = Auth0ManagementClient()
