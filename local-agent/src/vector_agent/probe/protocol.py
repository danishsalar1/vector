"""Bounded decoding and desktop-owned request/response correlation.

One request may be outstanding per session. Nonces are desktop challenges that a
response must echo, not credentials or hardware attestation. A future transport
must authenticate its peer separately. Rejection never produces a DiagnosticResult.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TypeVar
from uuid import uuid4

from pydantic import ValidationError

from vector_agent.models.probe import (
    MAX_COLLECTION_ITEMS,
    MAX_NESTING_DEPTH,
    MAX_OBJECT_KEYS,
    MAX_PROTOCOL_MESSAGE_BYTES,
    MAX_SEQUENCE_NUMBER,
    MAX_STRING_LENGTH,
    ProbeChallengeBinding,
    ProbeModel,
    ProbeOperation,
    ProbeProtocolVersion,
    ProbeRequestEnvelope,
    ProbeResponseEnvelope,
    require_utc,
)

CLOCK_SKEW_SECONDS = 5
MESSAGE_TTL_SECONDS = 30
SESSION_MAX_DURATION_SECONDS = 900
MAX_SESSION_REQUESTS = 4_096
MAX_SESSION_OBSERVATIONS = 4_096


class ProbeErrorCode(StrEnum):
    MALFORMED_MESSAGE = "MALFORMED_MESSAGE"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    BOUNDS_VIOLATION = "BOUNDS_VIOLATION"
    BINDING_MISMATCH = "BINDING_MISMATCH"
    REPLAY = "REPLAY"
    EXPIRED = "EXPIRED"
    INVALID_TIME = "INVALID_TIME"
    SESSION_CLOSED = "SESSION_CLOSED"
    REQUEST_PENDING = "REQUEST_PENDING"


class ProbeValidationError(ValueError):
    """Only a fixed code is exposed; never include input, tokens or parser errors."""

    def __init__(self, code: ProbeErrorCode) -> None:
        self.code = code
        super().__init__(f"Probe validation rejected: {code.value}.")


def generate_nonce() -> str:
    """32 cryptographically random bytes; 43 unpadded URL-safe characters."""
    return secrets.token_urlsafe(32)


def _reject_constant(_: str) -> object:
    raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)


def _integer(value: str) -> int:
    if len(value.lstrip("-")) > 19:
        raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
    result = int(value)
    if not -MAX_SEQUENCE_NUMBER <= result <= MAX_SEQUENCE_NUMBER:
        raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
    return result


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len(pairs) > MAX_OBJECT_KEYS:
        raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
        result[key] = value
    return result


def _check_depth(text: str) -> None:
    """Bound container depth BEFORE json.loads (root object is depth one)."""
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_NESTING_DEPTH:
                raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
        elif char in "]}":
            depth -= 1


def _check_values(value: object) -> None:
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
        # Lone escaped surrogates must not survive into logs/serialization.
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
    elif isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
        for item in value:
            _check_values(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_values(key)
            _check_values(item)


def decode_message(raw: bytes) -> dict[str, object]:
    """Reject malformed, ambiguous or oversized JSON before schema validation."""
    if type(raw) is not bytes:
        raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
    if len(raw) > MAX_PROTOCOL_MESSAGE_BYTES:
        raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
    failure: ProbeErrorCode | None = None
    value: object = None
    try:
        text = raw.decode("utf-8", errors="strict")
        _check_depth(text)
        value = json.loads(
            text, object_pairs_hook=_object, parse_int=_integer, parse_constant=_reject_constant
        )
        _check_values(value)
    except ProbeValidationError as exc:
        failure = exc.code
    except (ValueError, RecursionError):
        failure = ProbeErrorCode.MALFORMED_MESSAGE
    # Raise outside the except block so even exception context contains no input.
    if failure is not None:
        raise ProbeValidationError(failure)
    if not isinstance(value, dict):
        raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
    version = value.get("protocol_version")
    if type(version) is not int:
        raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
    if version != ProbeProtocolVersion.V1:
        raise ProbeValidationError(ProbeErrorCode.UNSUPPORTED_PROTOCOL)
    return value


_Model = TypeVar("_Model", bound=ProbeModel)


def _parse(raw: bytes, model: type[_Model]) -> _Model:
    decode_message(raw)
    result: _Model | None = None
    with suppress(ValidationError):
        result = model.model_validate_json(raw, strict=True)
    if result is None:
        raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
    return result


def parse_request(raw: bytes) -> ProbeRequestEnvelope:
    """Schema validation only; does not authorize dispatch or consume replay state."""
    return _parse(raw, ProbeRequestEnvelope)


def parse_response(raw: bytes) -> ProbeResponseEnvelope:
    """Schema validation only; ingestion must also use the session binding gate."""
    return _parse(raw, ProbeResponseEnvelope)


class ProbeProtocolSession:
    """Process-local replay state owned by the desktop, not supplied by the peer.

    The caller must supply a fresh device epoch from DeviceSessionManager when
    issuing/accepting messages and close this object on disconnect/revocation.
    No eviction of replay history: exhausting a bounded session requires a NEW
    session ID. Clock injection is for deterministic tests, not device input.
    """

    def __init__(
        self,
        *,
        device_id: str,
        device_epoch: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            type(device_id) is not str
            or re.fullmatch(r"(?:android|ios)-[0-9a-f]{12}", device_id) is None
        ):
            raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
        if type(device_epoch) is not int or not 0 <= device_epoch <= MAX_SEQUENCE_NUMBER:
            raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
        self._epoch = device_epoch
        self._device_id = device_id
        self._id = str(uuid4())
        self._clock = clock
        self._monotonic = monotonic
        self._created_at: datetime = require_utc(clock())
        self._created_mono = monotonic()
        self._last_now = self._created_at
        self._last_mono = self._created_mono
        self._next_sequence = 0
        self._last_accepted = -1
        self._pending: ProbeRequestEnvelope | None = None
        self._pending_mono: float | None = None
        self._dispatch_request: ProbeRequestEnvelope | None = None
        self._nonce_hashes: set[bytes] = set()
        self._observation_ids: set[str] = set()
        self._closed = False
        self._lock = threading.RLock()

    @property
    def device_id(self) -> str:
        """Opaque identity assigned locally; the peer never supplies this value."""
        return self._device_id

    @property
    def probe_session_id(self) -> str:
        return self._id

    def _now(self, current_device_epoch: int) -> datetime:
        if self._closed:
            raise ProbeValidationError(ProbeErrorCode.SESSION_CLOSED)
        if type(current_device_epoch) is not int or current_device_epoch != self._epoch:
            self.close()
            raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
        now: datetime = require_utc(self._clock())
        mono = self._monotonic()
        if now < self._last_now or mono < self._last_mono:
            self.close()
            raise ProbeValidationError(ProbeErrorCode.INVALID_TIME)
        self._last_now, self._last_mono = now, mono
        if (
            now >= self._created_at + timedelta(seconds=SESSION_MAX_DURATION_SECONDS)
            or mono - self._created_mono >= SESSION_MAX_DURATION_SECONDS
        ):
            self.close()
            raise ProbeValidationError(ProbeErrorCode.EXPIRED)
        return now

    def _pending_expired(self, now: datetime) -> bool:
        """Use the timing snapshot validated by _now, while holding the session lock."""
        if self._pending is None or self._pending_mono is None:
            raise ProbeValidationError(ProbeErrorCode.INVALID_TIME)
        return (
            now >= self._pending.expires_at
            or self._last_mono - self._pending_mono >= MESSAGE_TTL_SECONDS
        )

    def create_request(
        self,
        operation: ProbeOperation,
        *,
        current_device_epoch: int,
        binding: ProbeChallengeBinding | None = None,
    ) -> ProbeRequestEnvelope:
        with self._lock:
            now = self._now(current_device_epoch)
            if self._pending is not None:
                expired = self._pending
                if not self._pending_expired(now):
                    raise ProbeValidationError(ProbeErrorCode.REQUEST_PENDING)
                self.abandon_request(expired)
            if self._next_sequence >= MAX_SESSION_REQUESTS:
                raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
            nonce = generate_nonce()
            digest = hashlib.sha256(nonce.encode("ascii")).digest()
            if digest in self._nonce_hashes:
                raise ProbeValidationError(ProbeErrorCode.REPLAY)
            request: ProbeRequestEnvelope | None = None
            with suppress(ValidationError):
                request = ProbeRequestEnvelope(
                    protocol_version=1,
                    probe_session_id=self._id,
                    device_epoch=self._epoch,
                    binding=binding,
                    nonce=nonce,
                    sequence_number=self._next_sequence,
                    issued_at=now,
                    expires_at=min(
                        now + timedelta(seconds=MESSAGE_TTL_SECONDS),
                        self._created_at + timedelta(seconds=SESSION_MAX_DURATION_SECONDS),
                    ),
                    operation=operation,
                )
            if request is None:
                raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
            if binding is not None and not self._created_at <= binding.collection_not_before <= now:
                raise ProbeValidationError(ProbeErrorCode.INVALID_TIME)
            # Round-trip also enforces the shared wire byte/shape budget on outbound data.
            request = parse_request(request.model_dump_json().encode("utf-8"))
            self._nonce_hashes.add(digest)
            self._next_sequence += 1
            self._pending, self._pending_mono = request, self._last_mono
            return request

    def accept_response(
        self,
        raw: bytes,
        *,
        current_device_epoch: int,
        expected_request: ProbeRequestEnvelope,
    ) -> ProbeResponseEnvelope:
        if type(expected_request) is not ProbeRequestEnvelope:
            raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
        response = parse_response(raw)
        with self._lock:
            now = self._now(current_device_epoch)
            request = self._pending
            if response.sequence_number <= self._last_accepted:
                raise ProbeValidationError(ProbeErrorCode.REPLAY)
            if request is None or request != expected_request:
                raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
            if (
                response.probe_session_id != self._id
                or response.device_epoch != self._epoch
                or response.sequence_number != request.sequence_number
                or response.binding != request.binding
                or response.operation != request.operation
                or not hmac.compare_digest(response.nonce, request.nonce)
            ):
                raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
            if self._pending_expired(now) or now >= response.expires_at:
                raise ProbeValidationError(ProbeErrorCode.EXPIRED)
            skew = timedelta(seconds=CLOCK_SKEW_SECONDS)
            if (
                response.issued_at < request.issued_at - skew
                or response.issued_at > now + skew
                or response.expires_at > request.expires_at
                or response.expires_at - response.issued_at > timedelta(seconds=MESSAGE_TTL_SECONDS)
            ):
                raise ProbeValidationError(ProbeErrorCode.INVALID_TIME)
            ids = {observation.observation_id for observation in response.observations}
            if ids & self._observation_ids:
                raise ProbeValidationError(ProbeErrorCode.REPLAY)
            if len(self._observation_ids) + len(ids) > MAX_SESSION_OBSERVATIONS:
                raise ProbeValidationError(ProbeErrorCode.BOUNDS_VIOLATION)
            for observation in response.observations:
                if (
                    request.binding is None
                    or observation.collector_id != request.binding.diagnostic_id
                ):
                    raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
                if (
                    observation.collection_started_at < request.binding.collection_not_before
                    or observation.collection_completed_at > response.issued_at
                    or observation.collection_completed_at > now + skew
                ):
                    raise ProbeValidationError(ProbeErrorCode.INVALID_TIME)
            # Commit only after ALL schema, temporal, identity and observation checks.
            self._observation_ids.update(ids)
            self._last_accepted = response.sequence_number
            self.abandon_request(request)
            return response

    def require_pending(self, request: ProbeRequestEnvelope, *, current_device_epoch: int) -> None:
        """Dispatch gate: arbitrary typed requests cannot bypass desktop issuance."""
        with self._lock:
            now = self._now(current_device_epoch)
            if self._pending is None or request != self._pending:
                raise ProbeValidationError(ProbeErrorCode.BINDING_MISMATCH)
            if self._pending_expired(now):
                raise ProbeValidationError(ProbeErrorCode.EXPIRED)

    def abandon_request(self, request: ProbeRequestEnvelope) -> bool:
        """Remove exactly this pending request; stale/already-removed owners return False."""
        with self._lock:
            if type(request) is not ProbeRequestEnvelope:
                raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
            if self._pending == request:
                self._pending, self._pending_mono = None, None
                return True
            return False

    def claim_dispatch(self, request: ProbeRequestEnvelope, *, current_device_epoch: int) -> None:
        """Reserve one exchange across all adapters sharing this session."""
        with self._lock:
            if type(request) is not ProbeRequestEnvelope:
                raise ProbeValidationError(ProbeErrorCode.MALFORMED_MESSAGE)
            if self._dispatch_request is not None:
                raise ProbeValidationError(ProbeErrorCode.REQUEST_PENDING)
            try:
                self.require_pending(request, current_device_epoch=current_device_epoch)
            except ProbeValidationError:
                self.abandon_request(request)
                raise
            self._dispatch_request = request

    def finish_dispatch(self, request: ProbeRequestEnvelope) -> None:
        """Release only the claimed exchange and its still-pending request."""
        with self._lock:
            if self._dispatch_request == request:
                self._dispatch_request = None
                self.abandon_request(request)

    def close(self) -> None:
        """Idempotent invalidation. A closed object cannot be reopened."""
        with self._lock:
            self._closed = True
            self._pending, self._pending_mono = None, None
            self._dispatch_request = None
            self._nonce_hashes.clear()
            self._observation_ids.clear()
