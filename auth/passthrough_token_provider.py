"""
Passthrough Token Provider for Google Workspace MCP

Accepts externally-managed Bearer tokens without requiring OAuth client
credentials (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).

The token is assumed to be valid and refreshed by an external service.
A single call to Google's userinfo endpoint is made to resolve the user's
email address; no other validation is performed.

Usage:
    MCP_ENABLE_OAUTH21=true
    EXTERNAL_OAUTH21_PROVIDER=true
    MCP_TRUST_BEARER_TOKEN=true
"""

import logging
import time
from typing import List, Optional

from fastmcp.server.auth import AccessToken
from google.oauth2.credentials import Credentials

from auth.external_oauth_provider import get_session_time
from auth.oauth_types import WorkspaceAccessToken

logger = logging.getLogger(__name__)


class PassthroughTokenProvider:
    """
    Minimal auth provider that trusts externally-managed Bearer tokens.

    Unlike ExternalOAuthProvider, this class does not require OAuth client
    credentials.  It calls Google's userinfo API using only the raw access
    token to resolve the caller's email address, then lets all subsequent
    Google API calls use that token directly.
    """

    def __init__(self, required_scopes: Optional[List[str]] = None):
        self.required_scopes: List[str] = required_scopes or []

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """
        Resolve user identity from a ya29.* Bearer token.

        Calls Google's userinfo endpoint with the bare token (no client
        credentials needed).  Returns a WorkspaceAccessToken on success,
        None otherwise.
        """
        if not token.startswith("ya29."):
            logger.debug("PassthroughTokenProvider: skipping non-ya29 token")
            return None

        try:
            from auth.google_auth import get_user_info

            # Credentials built with just the token - client_id/secret are only
            # needed for token refresh, which never happens in passthrough mode.
            credentials = Credentials(token=token)

            user_info = get_user_info(credentials, skip_valid_check=True)

            if not user_info or not user_info.get("email"):
                logger.error(
                    "PassthroughTokenProvider: could not resolve user info from token"
                )
                return None

            email = user_info["email"]
            logger.info(f"PassthroughTokenProvider: resolved token for {email}")

            return WorkspaceAccessToken(
                token=token,
                scopes=self.required_scopes,
                expires_at=int(time.time()) + get_session_time(),
                claims={"email": email, "sub": user_info.get("id")},
                email=email,
                sub=user_info.get("id"),
            )

        except Exception as exc:
            logger.error(f"PassthroughTokenProvider: error resolving token: {exc}")
            return None

    def get_routes(self, **kwargs) -> list:
        """No protocol-level routes needed in passthrough mode."""
        return []
