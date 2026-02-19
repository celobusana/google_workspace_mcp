"""
Passthrough Token Provider for Google Workspace MCP

Accepts externally-managed Bearer tokens without requiring OAuth client
credentials (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).

The token is assumed to be valid and refreshed by an external service.
A single direct HTTP call to Google's userinfo endpoint is made to resolve
the user's email address; no other validation is performed.

Usage:
    MCP_ENABLE_OAUTH21=true
    EXTERNAL_OAUTH21_PROVIDER=true
    MCP_TRUST_BEARER_TOKEN=true
"""

import logging
import time
from typing import List, Optional

import httpx
from fastmcp.server.auth import AccessToken

from auth.external_oauth_provider import get_session_time
from auth.oauth_types import WorkspaceAccessToken

logger = logging.getLogger(__name__)

_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class PassthroughTokenProvider:
    """
    Minimal auth provider that trusts externally-managed Bearer tokens.

    Does NOT use googleapiclient or google.oauth2.credentials — those
    libraries trigger an automatic token refresh when they receive a 401,
    which fails without client_id/secret.

    Instead, makes a single direct HTTP GET to Google's userinfo endpoint
    to resolve the caller's email.  If the token is invalid/expired the
    endpoint returns 401 and verify_token() returns None (unauthenticated).
    """

    def __init__(self, required_scopes: Optional[List[str]] = None):
        self.required_scopes: List[str] = required_scopes or []

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """
        Resolve user identity from a ya29.* Bearer token via a direct
        HTTP request to Google's userinfo endpoint.

        Returns a WorkspaceAccessToken on success, None otherwise.
        """
        if not token.startswith("ya29."):
            logger.debug("PassthroughTokenProvider: skipping non-ya29 token")
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    _USERINFO_URL,
                    headers={"Authorization": f"Bearer {token}"},
                )

            if response.status_code != 200:
                logger.error(
                    "PassthroughTokenProvider: userinfo returned %s — token may be expired or lack userinfo scope",
                    response.status_code,
                )
                return None

            user_info = response.json()
            email = user_info.get("email")

            if not email:
                logger.error(
                    "PassthroughTokenProvider: userinfo response missing email field: %s",
                    user_info,
                )
                return None

            logger.info("PassthroughTokenProvider: resolved token for %s", email)

            return WorkspaceAccessToken(
                token=token,
                scopes=self.required_scopes,
                expires_at=int(time.time()) + get_session_time(),
                claims={"email": email, "sub": user_info.get("id")},
                email=email,
                sub=user_info.get("id"),
            )

        except Exception as exc:
            logger.error("PassthroughTokenProvider: error resolving token: %s", exc)
            return None

    def get_routes(self, **kwargs) -> list:
        """No protocol-level routes needed in passthrough mode."""
        return []
