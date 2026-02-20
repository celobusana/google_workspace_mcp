"""
Passthrough Token Provider for Google Workspace MCP

Accepts externally-managed Bearer tokens without requiring OAuth client
credentials (GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).

Two-layer design:
  Layer 1 — PassthroughAuthMiddleware (Starlette ASGI middleware)
      Runs before FastMCP processes the request.  Returns a proper HTTP 401
      when the token is expired or lacks required scopes.  On success it stores
      the resolved user info in a ContextVar so Layer 2 can reuse it.

  Layer 2 — PassthroughTokenProvider (FastMCP auth provider)
      Called by AuthInfoMiddleware during tool execution to populate
      authenticated_user in the FastMCP context.  Reads from the ContextVar
      set by Layer 1; falls back to a direct HTTP call when the middleware is
      not installed (e.g. stdio transport).

Usage:
    MCP_ENABLE_OAUTH21=true
    EXTERNAL_OAUTH21_PROVIDER=true
    MCP_TRUST_BEARER_TOKEN=true
"""

import contextvars
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from fastmcp.server.auth import AccessToken

from auth.external_oauth_provider import get_session_time
from auth.oauth_types import WorkspaceAccessToken

logger = logging.getLogger(__name__)

_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_DRIVE_ABOUT_URL = "https://www.googleapis.com/drive/v3/about?fields=user"

# Shared between the Starlette middleware and the FastMCP provider.
# Stores {"email": "...", "id": "..."} on success, None when not set.
_validated_user: contextvars.ContextVar[Optional[Dict[str, Any]]] = (
    contextvars.ContextVar("passthrough_validated_user", default=None)
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _resolve_user_info(
    token: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Resolve user identity from a ya29.* access token.

    Returns:
        (user_info, None)               — success; user_info has at least "email"
        (None, "token_expired")         — token is expired or revoked
        (None, "insufficient_scope")    — token lacks required scopes
        (None, "error")                 — unexpected error
    """
    auth_header = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # --- primary: userinfo endpoint (requires email/openid scope) ---
        ui_resp = await client.get(
            _USERINFO_URL, headers={"Authorization": auth_header}
        )

        if ui_resp.status_code == 200:
            data = ui_resp.json()
            if data.get("email"):
                return data, None
            return None, "error"

        if ui_resp.status_code == 401:
            logger.warning(
                "PassthroughAuthMiddleware: userinfo 401 — token expired or invalid"
            )
            return None, "token_expired"

        if ui_resp.status_code == 403:
            # Token may lack email scope; try Drive about as fallback.
            about_resp = await client.get(
                _DRIVE_ABOUT_URL, headers={"Authorization": auth_header}
            )
            if about_resp.status_code == 200:
                email = about_resp.json().get("user", {}).get("emailAddress")
                if email:
                    return {"email": email}, None
            if about_resp.status_code == 401:
                return None, "token_expired"
            # Both endpoints denied — truly insufficient scope.
            logger.warning(
                "PassthroughAuthMiddleware: 403 on userinfo and Drive about — "
                "token lacks required scopes"
            )
            return None, "insufficient_scope"

        logger.error(
            "PassthroughAuthMiddleware: unexpected userinfo status %s",
            ui_resp.status_code,
        )
        return None, "error"


async def _send_json_response(
    send: Callable,
    status_code: int,
    body: Dict[str, Any],
    extra_headers: Optional[List[Tuple[str, str]]] = None,
) -> None:
    """Send a JSON HTTP response through the raw ASGI send callable."""
    body_bytes = json.dumps(body).encode()
    headers: List[Tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body_bytes)).encode()),
    ]
    if extra_headers:
        for k, v in extra_headers:
            headers.append(
                (
                    k.encode() if isinstance(k, str) else k,
                    v.encode() if isinstance(v, str) else v,
                )
            )
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body_bytes, "more_body": False})


# ---------------------------------------------------------------------------
# Layer 1 — Starlette ASGI middleware
# ---------------------------------------------------------------------------

class PassthroughAuthMiddleware:
    """
    Pure ASGI middleware (no BaseHTTPMiddleware) that validates Bearer tokens
    at the HTTP transport level and returns 401 before FastMCP ever runs.

    Only intercepts POST/GET requests whose path ends with /mcp that carry a
    ya29.* Bearer token.  All other requests pass through unchanged.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        # Only guard the MCP endpoint.
        if not (path == "/mcp" or path.endswith("/mcp")):
            await self.app(scope, receive, send)
            return

        # Extract Authorization header from raw ASGI headers.
        headers_raw: List[Tuple[bytes, bytes]] = scope.get("headers", [])
        auth_value = ""
        for k, v in headers_raw:
            if k.lower() == b"authorization":
                auth_value = v.decode("utf-8", errors="replace")
                break

        if not auth_value.startswith("Bearer ya29."):
            # Not a ya29 token — pass through; FastMCP / existing auth handles it.
            await self.app(scope, receive, send)
            return

        token = auth_value[len("Bearer "):]

        try:
            user_info, error_type = await _resolve_user_info(token)
        except Exception as exc:
            logger.error("PassthroughAuthMiddleware: unexpected error: %s", exc)
            await _send_json_response(
                send, 500, {"error": "server_error", "message": "Token validation failed"}
            )
            return

        if error_type == "token_expired":
            await _send_json_response(
                send,
                401,
                {"error": "invalid_token", "message": "Token is expired"},
                [("WWW-Authenticate", 'Bearer error="invalid_token", error_description="Token is expired"')],
            )
            return

        if error_type == "insufficient_scope":
            # Include the required scopes so the caller knows what to request.
            try:
                from auth.scopes import get_current_scopes
                required = sorted(get_current_scopes())
            except Exception:
                required = []
            scope_str = " ".join(required)
            await _send_json_response(
                send,
                401,
                {
                    "error": "insufficient_scope",
                    "message": "Token does not have the required scope",
                    "required_scopes": required,
                },
                [
                    (
                        "WWW-Authenticate",
                        f'Bearer error="insufficient_scope", '
                        f'error_description="Token does not have the required scope", '
                        f'scope="{scope_str}"',
                    )
                ],
            )
            return

        if not user_info or not user_info.get("email"):
            await _send_json_response(
                send,
                401,
                {"error": "invalid_token", "message": "Token validation failed"},
            )
            return

        logger.info(
            "PassthroughAuthMiddleware: validated token for %s", user_info["email"]
        )

        # Store resolved user info for PassthroughTokenProvider (Layer 2).
        token_ctx = _validated_user.set(user_info)
        try:
            await self.app(scope, receive, send)
        finally:
            _validated_user.reset(token_ctx)


# ---------------------------------------------------------------------------
# Layer 2 — FastMCP auth provider
# ---------------------------------------------------------------------------

class PassthroughTokenProvider:
    """
    FastMCP auth provider for passthrough mode.

    Reads user info from the ContextVar set by PassthroughAuthMiddleware to
    avoid a second userinfo HTTP call.  Falls back to a direct call when the
    middleware is not installed (e.g. stdio transport or direct invocation).
    """

    def __init__(self, required_scopes: Optional[List[str]] = None) -> None:
        self.required_scopes: List[str] = required_scopes or []

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token.startswith("ya29."):
            logger.debug("PassthroughTokenProvider: skipping non-ya29 token")
            return None

        # Fast path — user info already resolved by PassthroughAuthMiddleware.
        user_info = _validated_user.get()

        if user_info is None:
            # Fallback: direct HTTP call (middleware not present or not yet run).
            try:
                user_info, error_type = await _resolve_user_info(token)
            except Exception as exc:
                logger.error("PassthroughTokenProvider: error resolving token: %s", exc)
                return None
            if not user_info:
                logger.error(
                    "PassthroughTokenProvider: could not resolve user info (%s)", error_type
                )
                return None

        email = user_info.get("email")
        if not email:
            return None

        logger.info("PassthroughTokenProvider: resolved token for %s", email)

        return WorkspaceAccessToken(
            token=token,
            client_id="passthrough",
            scopes=self.required_scopes,
            expires_at=int(time.time()) + get_session_time(),
            claims={"email": email, "sub": user_info.get("id") or user_info.get("sub")},
            email=email,
            sub=user_info.get("id") or user_info.get("sub"),
        )

    def get_routes(self, **kwargs) -> list:
        """No protocol-level routes needed in passthrough mode."""
        return []
