"""Real constant-time authorization logic and opt-in FastAPI dependency tests."""

from __future__ import annotations

import pickle
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from vector_agent.security import local_api_auth as module
from vector_agent.security.local_api_auth import (
    LOCAL_AUTH_HEADER,
    LocalApiAuth,
    LocalAuthOutcome,
    get_local_api_auth,
    require_local_authorization,
)


@pytest.mark.parametrize(
    "bad",
    [None, "", "wrong", "a" * 43, "a" * 10000, "é" * 43, "a" * 42 + "\n", True, 123, b"a" * 43],
)
def test_bad_credentials_reach_constant_time_comparison(
    bad: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = LocalApiAuth()
    original = module.hmac.compare_digest
    calls: list[tuple[int, int]] = []

    def spy(left: str, right: str) -> bool:
        calls.append((len(left), len(right)))
        return original(left, right)

    monkeypatch.setattr(module.hmac, "compare_digest", spy)
    assert auth.authorize(bad) == LocalAuthOutcome.UNAUTHORIZED
    assert calls == [(43, 43)]


def test_correct_token_and_redacted_holder(caplog: pytest.LogCaptureFixture) -> None:
    auth = LocalApiAuth()
    token = auth.token_for_local_bootstrap()
    assert len(token) == 43
    assert auth.authorize(token) == LocalAuthOutcome.AUTHORIZED
    assert token not in repr(auth) + str(auth) + caplog.text
    with pytest.raises(TypeError) as caught:
        pickle.dumps(auth)
    assert token not in str(caught.value)


def test_process_singleton_and_process_change(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = get_local_api_auth()
    assert get_local_api_auth() is auth
    token = auth.token_for_local_bootstrap()
    pid = module.os.getpid()
    monkeypatch.setattr(module.os, "getpid", lambda: pid + 1)
    new = get_local_api_auth()
    assert new is not auth
    assert new.authorize(token) == LocalAuthOutcome.UNAUTHORIZED


def app_client() -> TestClient:
    app = FastAPI()

    @app.get("/private", dependencies=[Depends(require_local_authorization)])
    def protected() -> dict[str, bool]:
        return {"authorized": True}

    @app.get("/existing")
    def existing() -> dict[str, bool]:
        return {"public": True}

    return TestClient(app)


def test_http_dependency_uses_header_only_and_keeps_other_routes_public() -> None:
    token = get_local_api_auth().token_for_local_bootstrap()
    with app_client() as client:
        assert client.get("/private", headers={LOCAL_AUTH_HEADER: token}).status_code == 200
        assert client.get("/existing").status_code == 200
        # Deliberately fabricated wrong token; never place a real credential in a URL.
        assert client.get("/private?token=fabricated").status_code == 401
        assert (
            client.get("/private", headers={"Authorization": "Bearer fabricated"}).status_code
            == 401
        )
        assert client.get("/private").json() == {"detail": "Local authorization required."}


def test_http_duplicate_and_malformed_headers_have_safe_failures() -> None:
    token = get_local_api_auth().token_for_local_bootstrap()
    with app_client() as client:
        for headers in (
            [(LOCAL_AUTH_HEADER, token), (LOCAL_AUTH_HEADER, token)],
            [(LOCAL_AUTH_HEADER, "SECRET_TEST_MARKER")],
            [(LOCAL_AUTH_HEADER, token + " ")],
        ):
            result = client.get("/private", headers=headers)
            assert result.status_code == 401
            assert result.json() == {"detail": "Local authorization required."}
            assert token not in result.text
            assert "SECRET_TEST_MARKER" not in result.text
