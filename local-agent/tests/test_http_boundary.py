"""MA-006: Host/Origin boundary for the loopback-only local agent.

These tests pin the middleware contract (400 malformed/missing/duplicate Host,
403 untrusted Host, 403 rejected Origin on state-changing requests), the
validated configuration, the wiring in ``create_app`` with the PRODUCTION
default settings, preserved CORS preflight enforcement, and that Probe routes
keep their own stricter checks. Header values are fabricated.

Host/Origin validation is not authentication: tests also pin that an absent
Origin is allowed through (native clients) and is not treated as a credential.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from vector_agent.core.config import AgentSettings
from vector_agent.main import create_app
from vector_agent.security import http_boundary
from vector_agent.security.http_boundary import (
    DEFAULT_TRUSTED_HOSTS,
    HttpBoundaryMiddleware,
    validate_allowed_origins,
    validate_trusted_hosts,
)
from vector_agent.security.local_api_auth import LOCAL_AUTH_HEADER, get_local_api_auth

VITE_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
PREVIEW_ORIGINS = ("http://localhost:4173", "http://127.0.0.1:4173")
HOST_REJECT = {"detail": "Host not permitted."}
HOST_INVALID = {"detail": "Invalid Host header."}
ORIGIN_REJECT = {"detail": "Origin not permitted."}
PROBE_PATH = "/api/v1/devices/android-0123456789ab/probe"


# --------------------------------------------------------------------------- helpers


async def _inner_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        await send({"type": "lifespan.startup.complete"})
        return
    if scope["type"] == "websocket":
        await receive()
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 1000})
        return
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _boundary(
    hosts: tuple[str, ...] = DEFAULT_TRUSTED_HOSTS,
    origins: tuple[str, ...] = (*VITE_ORIGINS, *PREVIEW_ORIGINS),
) -> HttpBoundaryMiddleware:
    return HttpBoundaryMiddleware(_inner_app, trusted_hosts=hosts, allowed_origins=origins)


def _call(
    middleware: HttpBoundaryMiddleware,
    *,
    method: str = "POST",
    headers: list[tuple[str, str]],
) -> tuple[int, dict[str, str] | None]:
    """Drive the middleware with a raw ASGI HTTP scope; return (status, json body or None)."""
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "method": method,
        "path": "/x",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers],
    }
    asyncio.run(middleware(scope, receive, send))
    status = sent[0]["status"]
    body = sent[1].get("body", b"")
    return status, (json.loads(body) if body else None)


GOOD_HOST = ("host", "127.0.0.1:8742")


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def production_settings(monkeypatch: pytest.MonkeyPatch) -> AgentSettings:
    """Settings exactly as shipped: the suite-wide test-host override is removed."""
    monkeypatch.delenv("VECTOR_TRUSTED_HOSTS", raising=False)
    monkeypatch.delenv("VECTOR_CORS_ORIGINS", raising=False)
    return AgentSettings(_env_file=None)


@pytest.fixture
def client(production_settings: AgentSettings) -> Any:
    with TestClient(create_app(production_settings), base_url="http://127.0.0.1:8742") as c:
        yield c


# --------------------------------------------------------------------------- defaults / config


def test_production_defaults_are_explicit_loopback_only(production_settings: AgentSettings) -> None:
    assert DEFAULT_TRUSTED_HOSTS == ("127.0.0.1", "localhost")
    assert production_settings.trusted_hosts == ["127.0.0.1", "localhost"]
    assert production_settings.cors_origins == [*VITE_ORIGINS, *PREVIEW_ORIGINS]
    assert production_settings.host == "127.0.0.1"
    for entry in production_settings.cors_origins:
        assert "*" not in entry and entry != "null"
    validate_trusted_hosts(production_settings.trusted_hosts)
    validate_allowed_origins(production_settings.cors_origins)


@pytest.mark.parametrize(
    "bad",
    [
        ["*"],
        ["*.example.com"],
        [""],
        [" localhost"],
        ["localhost:5173"],
        ["http://localhost"],
        ["LOCALHOST"],
        ["local host"],
        ["localhost/"],
        [],
    ],
)
def test_trusted_hosts_config_rejects_wildcards_and_malformed_entries(bad: list[str]) -> None:
    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None, trusted_hosts=bad)
    with pytest.raises(ValueError):
        validate_trusted_hosts(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "*",
        "null",
        "",
        "localhost:5173",
        "http://localhost:5173/",
        "http://localhost:5173/path",
        "http://",
        "ftp://localhost:5173",
        "http://user@localhost:5173",
        "http://LOCALHOST:5173",
        "http://localhost:99999",
        "http://localhost:0",
        "http://localhost:",
        "http://*.example.com",
        "http://localhost:5173?x=1",
        "http://localhost:5173#f",
        "http://[::1]:5173",
    ],
)
def test_cors_origins_config_rejects_wildcards_null_and_malformed_entries(bad: str) -> None:
    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None, cors_origins=[bad])
    with pytest.raises(ValueError):
        validate_allowed_origins([bad])


def test_environment_override_is_validated_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTOR_CORS_ORIGINS", '["*"]')
    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None)
    monkeypatch.delenv("VECTOR_CORS_ORIGINS")
    monkeypatch.setenv("VECTOR_TRUSTED_HOSTS", '["*"]')
    with pytest.raises(ValidationError):
        AgentSettings(_env_file=None)


def test_middleware_construction_fails_closed_never_open() -> None:
    with pytest.raises(ValueError):
        HttpBoundaryMiddleware(_inner_app, trusted_hosts=[], allowed_origins=VITE_ORIGINS)
    with pytest.raises(ValueError):
        HttpBoundaryMiddleware(_inner_app, trusted_hosts=["*"], allowed_origins=VITE_ORIGINS)
    with pytest.raises(ValueError):
        HttpBoundaryMiddleware(_inner_app, trusted_hosts=["localhost"], allowed_origins=["*"])
    with pytest.raises(ValueError):
        HttpBoundaryMiddleware(_inner_app, trusted_hosts=["localhost"], allowed_origins=["null"])


def test_empty_origin_allow_list_rejects_every_present_origin_on_unsafe_methods() -> None:
    mw = _boundary(origins=())
    assert _call(mw, headers=[GOOD_HOST, ("origin", "http://localhost:5173")]) == (
        403,
        ORIGIN_REJECT,
    )
    # An absent Origin is still not a rejection reason (native clients).
    assert _call(mw, headers=[GOOD_HOST])[0] == 204


# --------------------------------------------------------------------------- Host contract


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.0.0.1:8742",
        "127.0.0.1:5173",
        "localhost",
        "localhost:5173",
        "localhost:4173",
        "LOCALHOST:5173",
        "LocalHost",
    ],
)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_authorized_loopback_host_is_accepted(host: str, method: str) -> None:
    assert _call(_boundary(), method=method, headers=[("host", host)])[0] == 204


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8742",
        "127.0.0.1.evil.example",
        "localhost.evil.example:5173",
        "evil-localhost",
        "localhost.",
        "127.0.0.2",
        "0.0.0.0:8742",
        "169.254.169.254",
        "attacker.test",
    ],
)
@pytest.mark.parametrize("method", ["GET", "POST", "OPTIONS", "DELETE"])
def test_hostile_or_unexpected_host_is_rejected_403(host: str, method: str) -> None:
    assert _call(_boundary(), method=method, headers=[("host", host)]) == (403, HOST_REJECT)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "127.0.0.1:",
        "127.0.0.1:99999",
        "127.0.0.1:0",
        "localhost:abc",
        "[::1]:8742",
        "127.0.0.1@evil.example",
        "evil.example/127.0.0.1",
        "127.0.0.1 evil.example",
        "127.0.0.1,evil.example",
        "http://127.0.0.1",
        "user:pw@localhost",
        "localhost:5173:5173",
    ],
)
def test_malformed_host_is_rejected_400(host: str) -> None:
    assert _call(_boundary(), headers=[("host", host)]) == (400, HOST_INVALID)


def test_missing_host_is_rejected_400() -> None:
    assert _call(_boundary(), headers=[]) == (400, HOST_INVALID)
    assert _call(_boundary(), method="GET", headers=[]) == (400, HOST_INVALID)


def test_duplicate_host_headers_are_rejected_400_even_if_both_are_trusted() -> None:
    headers = [("host", "127.0.0.1:8742"), ("host", "localhost:8742")]
    assert _call(_boundary(), headers=headers) == (400, HOST_INVALID)
    headers = [("host", "127.0.0.1:8742"), ("host", "evil.example")]
    assert _call(_boundary(), headers=headers) == (400, HOST_INVALID)


def test_host_check_runs_before_origin_check() -> None:
    headers = [("host", "evil.example"), ("origin", "http://localhost:5173")]
    assert _call(_boundary(), headers=headers) == (403, HOST_REJECT)


# --------------------------------------------------------------------------- Origin contract


@pytest.mark.parametrize("origin", [*VITE_ORIGINS, *PREVIEW_ORIGINS])
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_authorized_vite_origin_is_accepted_on_unsafe_methods(origin: str, method: str) -> None:
    assert _call(_boundary(), method=method, headers=[GOOD_HOST, ("origin", origin)])[0] == 204


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "NULL",
        "",
        "*",
        "https://evil.example",
        "http://evil.example",
        "http://localhost:5174",
        "http://localhost",
        "https://localhost:5173",
        "http://localhost:5173/",
        "http://localhost:5173.evil.example",
        "http://evil.example:5173",
        "http://127.0.0.1:5173@evil.example",
        "HTTP://LOCALHOST:5173",
        "http://LOCALHOST:5173",
        "http://[::1]:5173",
        " http://localhost:5173",
        "http://localhost:5173 ",
        "file://",
        "chrome-extension://abcdefghijklmnop",
        "http://localhost:5173, http://evil.example",
        "garbage\x7f",
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "TRACE", "FOO"])
def test_unauthorized_malformed_or_null_origin_is_rejected_403_on_unsafe_methods(
    origin: str, method: str
) -> None:
    result = _call(_boundary(), method=method, headers=[GOOD_HOST, ("origin", origin)])
    assert result == (403, ORIGIN_REJECT)


def test_multiple_origin_headers_are_rejected_even_if_each_is_allowed() -> None:
    headers = [GOOD_HOST, ("origin", VITE_ORIGINS[0]), ("origin", VITE_ORIGINS[1])]
    assert _call(_boundary(), headers=headers) == (403, ORIGIN_REJECT)
    headers = [GOOD_HOST, ("origin", VITE_ORIGINS[0]), ("origin", "https://evil.example")]
    assert _call(_boundary(), headers=headers) == (403, ORIGIN_REJECT)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_absent_origin_is_allowed_for_native_clients_but_is_not_authentication(
    method: str,
) -> None:
    # Allowed through the boundary ...
    assert _call(_boundary(), method=method, headers=[GOOD_HOST])[0] == 204
    # ... and the Host allow-list still applies to it (no Origin does not bypass Host).
    assert _call(_boundary(), method=method, headers=[("host", "evil.example")])[0] == 403


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_safe_methods_are_not_origin_checked_but_are_host_checked(method: str) -> None:
    # CORS (browser read policy / preflight allow-list) governs these; see preflight tests.
    assert _call(_boundary(), method=method, headers=[GOOD_HOST, ("origin", "null")])[0] == 204
    assert _call(_boundary(), method=method, headers=[("host", "evil.example")])[0] == 403


def test_rejection_bodies_and_logs_never_echo_request_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[str] = []

    class Recorder:
        def warning(self, fmt: str, *args: object) -> None:
            logged.append(fmt % args)

    monkeypatch.setattr(http_boundary, "logger", Recorder())
    marker = "ATTACKER-CONTROLLED-MARKER-7f3a"
    status, body = _call(_boundary(), headers=[("host", f"{marker}.example")])
    assert status == 403 and body == HOST_REJECT
    status, body = _call(_boundary(), headers=[GOOD_HOST, ("origin", f"https://{marker}.example")])
    assert status == 403 and body == ORIGIN_REJECT
    assert logged == [
        "HTTP boundary rejection | reason=host_untrusted | method=POST",
        "HTTP boundary rejection | reason=origin_rejected | method=POST",
    ]
    assert all(marker not in line for line in logged)


# --------------------------------------------------------------------------- websocket / lifespan


def _ws(headers: list[tuple[str, str]]) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "websocket.connect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "websocket",
        "path": "/ws",
        "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in headers],
    }
    asyncio.run(_boundary()(scope, receive, send))
    return sent


def test_websocket_handshake_is_checked_for_host_and_origin() -> None:
    assert _ws([GOOD_HOST])[0]["type"] == "websocket.accept"
    assert _ws([GOOD_HOST, ("origin", VITE_ORIGINS[0])])[0]["type"] == "websocket.accept"
    for headers in (
        [("host", "evil.example")],
        [GOOD_HOST, ("origin", "https://evil.example")],
        [GOOD_HOST, ("origin", "null")],
    ):
        assert _ws(headers) == [{"type": "websocket.close", "code": 1008}]


def test_lifespan_scope_passes_through() -> None:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(_boundary()({"type": "lifespan"}, receive, send))
    assert sent == [{"type": "lifespan.startup.complete"}]


# --------------------------------------------------------------------------- app wiring (production defaults)


def test_app_serves_authorized_loopback_host_and_existing_endpoint_is_unchanged(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"
    for host in ("localhost:5173", "127.0.0.1:5173", "localhost:4173"):
        assert client.get("/api/v1/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "testserver", "test", "127.0.0.1.evil.example"])
def test_app_rejects_hostile_host_with_production_defaults(client: TestClient, host: str) -> None:
    response = client.get("/api/v1/health", headers={"Host": host})
    assert response.status_code == 403 and response.json() == HOST_REJECT
    # State-changing request with a hostile Host is also rejected before the route runs.
    response = client.post("/api/v1/scans", json={}, headers={"Host": host})
    assert response.status_code == 403 and response.json() == HOST_REJECT


def test_app_rejects_hostile_origin_on_every_state_changing_route(client: TestClient) -> None:
    hostile = {"Origin": "https://evil.example"}
    for path in (
        "/api/v1/scans",
        "/api/v1/scans/plan",
        "/api/v1/devices/ios-0123456789ab/pair",
        f"{PROBE_PATH}/discover",
    ):
        response = client.post(path, json={}, headers=hostile)
        assert response.status_code == 403, path
        assert response.json() == ORIGIN_REJECT, path
    assert client.delete("/api/v1/scans/x", headers=hostile).status_code == 403
    response = client.post("/api/v1/scans", json={}, headers={"Origin": "null"})
    assert response.status_code == 403 and response.json() == ORIGIN_REJECT


@pytest.mark.parametrize("origin", [*VITE_ORIGINS, *PREVIEW_ORIGINS, None])
def test_app_lets_vite_origins_and_native_clients_reach_the_route(
    client: TestClient, origin: str | None
) -> None:
    headers = {"Origin": origin} if origin else {}
    # `{}` fails request validation in the route itself (422): proof the request got
    # past the boundary and was handled by the real endpoint, with its contract intact.
    response = client.post("/api/v1/scans/plan", json={}, headers=headers)
    assert response.status_code == 422
    assert "detail" in response.json() and response.json() != ORIGIN_REJECT


def test_vite_proxy_style_request_passes_host_and_origin_together(client: TestClient) -> None:
    # Vite (changeOrigin: false) forwards the browser's own Host and Origin.
    headers = {"Host": "localhost:5173", "Origin": "http://localhost:5173"}
    assert client.post("/api/v1/scans/plan", json={}, headers=headers).status_code == 422
    headers = {"Host": "127.0.0.1:4173", "Origin": "http://127.0.0.1:4173"}
    assert client.post("/api/v1/scans/plan", json={}, headers=headers).status_code == 422


# --------------------------------------------------------------------------- CORS preflight allow-list preserved


def test_preflight_allow_list_is_still_enforced(client: TestClient) -> None:
    request_headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    ok = client.options("/api/v1/scans", headers=request_headers)
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "*" not in ok.headers.get("access-control-allow-origin", "")
    assert "access-control-allow-credentials" not in ok.headers

    for origin in ("https://evil.example", "null", "http://localhost:5174"):
        denied = client.options("/api/v1/scans", headers={**request_headers, "Origin": origin})
        assert denied.status_code == 400, origin
        assert "access-control-allow-origin" not in denied.headers

    # The Probe authorization header can never be sent cross-origin by a browser.
    probe_header = {**request_headers, "Access-Control-Request-Headers": LOCAL_AUTH_HEADER}
    assert client.options("/api/v1/scans", headers=probe_header).status_code == 400
    # Disallowed method.
    put = {**request_headers, "Access-Control-Request-Method": "PUT"}
    assert client.options("/api/v1/scans", headers=put).status_code == 400


def test_preflight_with_hostile_host_is_rejected_before_cors(client: TestClient) -> None:
    response = client.options(
        "/api/v1/scans",
        headers={
            "Host": "evil.example",
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 403 and response.json() == HOST_REJECT
    assert "access-control-allow-origin" not in response.headers


# --------------------------------------------------------------------------- Probe protections preserved


def test_probe_routes_retain_token_and_strict_origin_rejection(client: TestClient) -> None:
    token = {LOCAL_AUTH_HEADER: get_local_api_auth().token_for_local_bootstrap()}

    # Token still required (the boundary adds nothing that replaces it).
    assert client.get(PROBE_PATH).status_code == 401
    assert client.post(f"{PROBE_PATH}/discover").status_code == 401
    assert (
        client.post(f"{PROBE_PATH}/discover", headers={LOCAL_AUTH_HEADER: "x" * 43}).status_code
        == 401
    )

    # Even an Origin that the boundary AUTHORIZES (the Vite origin) is still rejected by
    # the Probe guard: Probe stays native/in-process only.
    for origin in (*VITE_ORIGINS, "https://evil.example"):
        assert client.get(PROBE_PATH, headers={**token, "Origin": origin}).status_code == 403
    allowed_origin_post = client.post(
        f"{PROBE_PATH}/discover", headers={**token, "Origin": VITE_ORIGINS[0]}
    )
    assert allowed_origin_post.status_code == 403
    assert allowed_origin_post.json() == {"detail": "Local control required."}

    # Hostile Host is still refused (now by the outer boundary; Probe's own check remains).
    assert client.get(PROBE_PATH, headers={**token, "Host": "hostile.example"}).status_code == 403

    # Native client path (token, no Origin, loopback Host) is unchanged.
    assert client.get(PROBE_PATH, headers=token).status_code == 409
    assert client.post(f"{PROBE_PATH}/discover", headers=token).status_code == 409


def test_probe_guard_still_rejects_hostile_host_when_boundary_is_bypassed() -> None:
    """Defense in depth: the Probe guard is independent of the boundary middleware."""
    from vector_agent.api.probe import local_control

    class FakeURL:
        hostname = "hostile.example"

    class FakeRequest:
        url = FakeURL()

        class headers:  # noqa: N801
            @staticmethod
            def getlist(name: str) -> list[str]:
                return (
                    [get_local_api_auth().token_for_local_bootstrap()]
                    if "Authorization" in name
                    else []
                )

    with pytest.raises(Exception, match="Local control required") as exc_info:
        asyncio.run(local_control(FakeRequest()))  # type: ignore[arg-type]
    assert getattr(exc_info.value, "status_code", None) == 403
