"""Opt-in, process-local authorization for FUTURE privileged Probe routes.

No existing route is modified. The header token is a local bearer credential,
not phone authentication, user consent, TLS, Origin validation or attestation.
Trusted local bootstrap may export it explicitly; there is no public token route.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import threading
from enum import StrEnum
from typing import Never

from fastapi import HTTPException, Request

LOCAL_AUTH_HEADER = "X-Vector-Local-Authorization"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}", flags=re.ASCII)


class LocalAuthOutcome(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    UNAUTHORIZED = "UNAUTHORIZED"


class LocalApiAuth:
    """A non-serializable credential holder with redacted repr and fixed failures."""

    __slots__ = ("_token",)

    def __init__(self) -> None:
        self._token = secrets.token_urlsafe(32)

    def __repr__(self) -> str:
        return "LocalApiAuth(<redacted>)"

    def __reduce__(self) -> Never:
        raise TypeError("Local authorization credentials cannot be serialized.")

    def token_for_local_bootstrap(self) -> str:
        """Trusted in-process bootstrap ONLY. Never return via an API or persist."""
        return self._token

    def authorize(self, supplied: object) -> LocalAuthOutcome:
        valid_shape = type(supplied) is str and _TOKEN_PATTERN.fullmatch(supplied) is not None
        # Even malformed/missing input takes the same fixed-length comparison path.
        candidate = supplied if valid_shape and isinstance(supplied, str) else "!" * 43
        matches = hmac.compare_digest(self._token, candidate)
        if valid_shape and matches:
            return LocalAuthOutcome.AUTHORIZED
        return LocalAuthOutcome.UNAUTHORIZED


_auth_lock = threading.Lock()
_process_auth: LocalApiAuth | None = None
_process_id: int | None = None


def get_local_api_auth() -> LocalApiAuth:
    """Lazy process-scoped credential; a fork must not reuse the parent's token."""
    global _process_auth, _process_id
    with _auth_lock:
        pid = os.getpid()
        if _process_auth is None or _process_id != pid:
            _process_auth = LocalApiAuth()
            _process_id = pid
        return _process_auth


async def require_local_authorization(request: Request) -> None:
    """FastAPI dependency: headers only, rejecting duplicates and query credentials.

    Manually inspect headers so FastAPI validation errors cannot echo a credential.
    No URL/query-string token is ever used as authorization.
    """
    values = request.headers.getlist(LOCAL_AUTH_HEADER)
    supplied = values[0] if len(values) == 1 else None
    if get_local_api_auth().authorize(supplied) != LocalAuthOutcome.AUTHORIZED:
        raise HTTPException(status_code=401, detail="Local authorization required.")
