"""Describe a bearer token in logs without ever revealing it.

Investigation instrument. Added after an incident where this server rejected a
caller's bearer token and logged nothing: every rejection path for a token that
is not ``ya29.*`` is ``logger.debug``, so in production (INFO) the request
simply produced "OAuth 2.1 mode requires an authenticated user ... but none was
found" with no way to tell what had actually arrived.

Nothing here is reversible. It emits the token FAMILY (derived from public,
documented prefixes -- not secrets), the length, and 8 hex characters of a
sha256. The digest exists to correlate the same token across services; it
cannot reconstruct anything.
"""

import hashlib
from typing import Optional

_GOOGLE_ACCESS_PREFIX = "ya29."
_GOOGLE_REFRESH_PREFIX = "1//"
_BEARER_PREFIX = "Bearer "


def _shape(token: str) -> str:
    if token.startswith(_GOOGLE_ACCESS_PREFIX):
        return "google_access"
    if token.startswith(_GOOGLE_REFRESH_PREFIX):
        # A refresh token sent where an access token was expected.
        return "google_refresh"
    if token.startswith(_BEARER_PREFIX):
        # `Authorization: Bearer Bearer <token>` -- header built twice upstream.
        return "double_bearer"
    if token.count(".") == 2 and token.startswith("ey"):
        return "jwt"
    return "unknown"


def token_shape(token: Optional[str]) -> str:
    """Return a safe description of a token, for logging.

    Examples::

        shape=google_access len=254 sha=a1b2c3d4
        shape=empty len=0
        shape=jwt len=1402 sha=99ff00aa
        shape=google_access len=255 sha=1122eeff ws=1
    """
    if token is None:
        return "shape=none len=0"
    if not token:
        return "shape=empty len=0"

    stripped = token.strip()
    # Leading/trailing whitespace breaks every prefix comparison downstream and
    # is invisible in any log that prints the raw value.
    whitespace = "" if stripped == token else " ws=1"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]
    return f"shape={_shape(stripped)} len={len(token)} sha={digest}{whitespace}"
