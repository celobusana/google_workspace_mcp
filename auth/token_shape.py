"""Describe a bearer token in logs without ever revealing it.

Deliberately provider-agnostic: it reports facts that hold for any opaque
bearer -- length, whether it parses as a JWT, whether it carries stray
whitespace -- plus a digest for correlation. It does NOT classify by issuer
prefix. The caller already knows why it is rejecting a token (it is standing in
that branch); duplicating a prefix table here would mean two places to update
when a provider changes its format, and the log would be the one that silently
goes stale.

Nothing is reversible. The digest is 8 hex of sha256 and serves one purpose:
comparing the SAME string across services. Equal at both ends proves the value
travelled intact; different proves it did not.
"""

import hashlib
from typing import Optional


def _looks_like_jwt(token: str) -> bool:
    """Three dot-separated segments with a base64url header -- enough to tell
    an ID token from an opaque access token without decoding anything or
    knowing the issuer."""
    parts = token.split(".")
    return len(parts) == 3 and all(parts) and token.startswith("ey")


def token_shape(token: Optional[str]) -> str:
    """Return a safe description of a token, for logging.

    Examples::

        len=254 sha=a1b2c3d4 jwt=0
        len=1402 sha=99ff00aa jwt=1
        len=255 sha=1122eeff jwt=0 ws=1
        empty
    """
    if token is None:
        return "absent"
    if not token:
        return "empty"

    stripped = token.strip()
    # Leading/trailing whitespace breaks every prefix comparison downstream and
    # is invisible in any log that prints the raw value.
    whitespace = "" if stripped == token else " ws=1"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]
    jwt = "1" if _looks_like_jwt(stripped) else "0"
    return f"len={len(token)} sha={digest} jwt={jwt}{whitespace}"
