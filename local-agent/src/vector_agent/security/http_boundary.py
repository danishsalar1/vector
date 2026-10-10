"""HTTP Host/Origin boundary for the loopback-only local agent (MA-006).

Scope and limits (read before relying on this):

* The agent binds ``127.0.0.1``. A web page the user visits can still make the
  browser send requests to it (cross-site requests) or, through DNS rebinding,
  make an attacker-controlled hostname resolve to ``127.0.0.1``. This boundary
  closes those two browser-mediated paths:
  - ``Host`` must be an explicitly trusted loopback hostname, so a rebound
    attacker hostname is rejected.
  - On state-changing requests a present ``Origin`` must exactly match an
    explicitly configured origin, so a hostile page cannot drive writes.
* An absent ``Origin`` is NOT authentication. Native/local clients omit it and
  keep working; any process on this machine can still call the API. This layer
  is not user authentication, not a substitute for the Probe local token, and
  does not defend against local malware or other processes on the same host.
* ``Origin`` is not checked on safe methods (GET/HEAD/OPTIONS): the browser's
  CORS policy governs cross-origin reads and ``CORSMiddleware`` answers
  preflights from the same allow-list. Probe routes keep their own, stricter,
  Origin/Host/token checks; this layer only adds to them.

Status contract: ``400`` for a malformed, missing or duplicated ``Host``;
``403`` for a well-formed but untrusted ``Host``; ``403`` for a rejected
``Origin``. Bodies are fixed strings and never echo request data.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, MutableMapping
from typing import Any

from vector_agent.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TRUSTED_HOSTS: tuple[str, ...] = ("127.0.0.1", "localhost")

#: Methods that do not change state. Everything else (including unknown
#: methods) is treated as state-changing and gets the Origin check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_HOST_HEADER = re.compile(r"(?P<host>[A-Za-z0-9.-]+)(?::(?P<port>[0-9]{1,5}))?", re.ASCII)
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", re.ASCII)
_ORIGIN = re.compile(
    r"https?://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?",
    re.ASCII,
)

Scope = MutableMapping[str, Any]


def validate_trusted_hosts(hosts: Collection[str]) -> tuple[str, ...]:
    """Return a validated, lower-cased host allow-list or raise ``ValueError``.

    Entries are bare hostnames or IPv4 literals: no wildcard, scheme, port or
    whitespace. An empty list is rejected so the boundary can never fail open.
    """
    if not hosts:
        raise ValueError("trusted_hosts must contain at least one explicit hostname.")
    cleaned: list[str] = []
    for host in hosts:
        if not isinstance(host, str) or _HOSTNAME.fullmatch(host) is None:
            raise ValueError("trusted_hosts entries must be explicit lower-case hostnames.")
        cleaned.append(host)
    return tuple(dict.fromkeys(cleaned))


def validate_allowed_origins(origins: Collection[str]) -> tuple[str, ...]:
    """Return a validated origin allow-list or raise ``ValueError``.

    Each entry must be exactly ``scheme://host[:port]`` with a lower-case host:
    no ``*``, ``null``, path, trailing slash, userinfo, query or fragment. An
    empty list is allowed (every present Origin on a state-changing request is
    then rejected).
    """
    cleaned: list[str] = []
    for origin in origins:
        if not isinstance(origin, str) or not _origin_is_valid(origin):
            raise ValueError("cors_origins entries must be explicit scheme://host[:port] origins.")
        cleaned.append(origin)
    return tuple(dict.fromkeys(cleaned))


def _origin_is_valid(origin: str) -> bool:
    if _ORIGIN.fullmatch(origin) is None:
        return False
    port = origin.rsplit(":", 1)[-1] if origin.count(":") == 2 else None
    return port is None or 0 < int(port) <= 65535


def _single_header(scope: Scope, name: bytes) -> tuple[int, str | None]:
    values = [value for key, value in scope.get("headers", ()) if key.lower() == name]
    if len(values) != 1:
        return len(values), None
    return 1, values[0].decode("latin-1")


class HttpBoundaryMiddleware:
    """Pure-ASGI Host allow-list and state-changing Origin allow-list."""

    def __init__(
        self,
        app: Any,
        *,
        trusted_hosts: Collection[str],
        allowed_origins: Collection[str],
    ) -> None:
        self.app = app
        self._hosts = frozenset(validate_trusted_hosts(trusted_hosts))
        self._origins = frozenset(validate_allowed_origins(allowed_origins))

    async def __call__(self, scope: Scope, receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        rejection = self._evaluate(scope)
        if rejection is None:
            await self.app(scope, receive, send)
            return
        status, reason, detail = rejection
        logger.warning(
            "HTTP boundary rejection | reason=%s | method=%s",
            reason,
            scope.get("method", scope["type"]),
        )
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"detail": detail}).encode("ascii")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _evaluate(self, scope: Scope) -> tuple[int, str, str] | None:
        host_count, host_value = _single_header(scope, b"host")
        if host_value is None:
            reason = "host_missing" if host_count == 0 else "host_duplicate"
            return 400, reason, "Invalid Host header."
        match = _HOST_HEADER.fullmatch(host_value)
        if match is None or (match["port"] is not None and not 0 < int(match["port"]) <= 65535):
            return 400, "host_malformed", "Invalid Host header."
        if match["host"].lower() not in self._hosts:
            return 403, "host_untrusted", "Host not permitted."

        method = str(scope.get("method", "")).upper()
        if scope["type"] == "http" and method in SAFE_METHODS:
            return None
        origin_count, origin_value = _single_header(scope, b"origin")
        if origin_count == 0:
            return None
        if origin_value is None or origin_value not in self._origins:
            return 403, "origin_rejected", "Origin not permitted."
        return None
