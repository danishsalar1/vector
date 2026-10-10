"""Abstract transport with reusable validation, cancellation and cleanup behavior.

There is deliberately no socket, ADB, URL, path or network dependency here.
Concrete adapters must bound reads BEFORE allocating a whole payload and honor
the monotonic deadline/cancellation during I/O. This base also rejects late replies;
it cannot forcibly interrupt an adapter that violates that cooperative contract.
"""

from __future__ import annotations

import math
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from vector_agent.evidence.validation import ValidatedProbeResponse, ingest_probe_response
from vector_agent.models.probe import MAX_PROTOCOL_MESSAGE_BYTES, ProbeRequestEnvelope
from vector_agent.probe.protocol import ProbeErrorCode, ProbeProtocolSession, ProbeValidationError

MAX_TRANSPORT_TIMEOUT_SECONDS = 30.0


class ProbeTransportStatus(StrEnum):
    RECEIVED = "RECEIVED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    PROTOCOL_VIOLATION = "PROTOCOL_VIOLATION"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    BOUNDS_VIOLATION = "BOUNDS_VIOLATION"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"
    BUSY = "BUSY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ProbeTransportReply:
    """Untrusted transport bytes or a typed error. Never expose payload in repr."""

    status: ProbeTransportStatus
    payload: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ProbeTransportResult:
    status: ProbeTransportStatus
    response: ValidatedProbeResponse | None = None


@dataclass(frozen=True)
class ProbeCancellation:
    _caller: threading.Event = field(repr=False)
    _closed: threading.Event = field(repr=False)

    def is_cancelled(self) -> bool:
        return self._caller.is_set() or self._closed.is_set()


class ProbeTransport(ABC):
    """One desktop session and one outstanding request per transport instance."""

    def __init__(
        self,
        *,
        session: ProbeProtocolSession,
        current_device_epoch: Callable[[], int],
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._current_epoch = current_device_epoch
        self._monotonic = monotonic
        self._closed = threading.Event()
        self._busy = False
        self._lock = threading.Lock()

    @abstractmethod
    def _exchange(
        self,
        request: ProbeRequestEnvelope,
        *,
        deadline: float,
        cancellation: ProbeCancellation,
    ) -> ProbeTransportReply:
        """Adapter boundary. Authenticate the peer and return bounded control bytes."""

    @abstractmethod
    def _cleanup(self) -> None:
        """Release owned resources only; must unblock in-flight I/O promptly."""

    def request(
        self,
        request: ProbeRequestEnvelope,
        *,
        timeout_seconds: float,
        cancellation: threading.Event,
    ) -> ProbeTransportResult:
        if (
            type(timeout_seconds) not in (int, float)
            or not 0 < timeout_seconds <= MAX_TRANSPORT_TIMEOUT_SECONDS
        ):
            return ProbeTransportResult(ProbeTransportStatus.BOUNDS_VIOLATION)
        with self._lock:
            if self._closed.is_set():
                return ProbeTransportResult(ProbeTransportStatus.CLOSED)
            if self._busy:
                return ProbeTransportResult(ProbeTransportStatus.BUSY)
            self._busy = True
        claimed = False
        # Cancellation (caller event or transport close) explains any exchange failure that
        # follows it: closing a socket under a blocked read surfaces as an arbitrary OSError,
        # and closing the session as SESSION_CLOSED. Report those as CANCELLED, never as a
        # generic disconnect, error or session expiry.
        token = ProbeCancellation(cancellation, self._closed)
        try:
            self._session.claim_dispatch(request, current_device_epoch=self._current_epoch())
            claimed = True
            start = self._monotonic()
            deadline = start + timeout_seconds
            if token.is_cancelled():
                return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
            reply = self._exchange(request, deadline=deadline, cancellation=token)
            if token.is_cancelled():
                return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
            now = self._monotonic()
            if not math.isfinite(now) or now < start or now >= deadline:
                return ProbeTransportResult(ProbeTransportStatus.TIMEOUT)
            if type(reply) is not ProbeTransportReply or not isinstance(
                reply.status, ProbeTransportStatus
            ):
                return ProbeTransportResult(ProbeTransportStatus.PROTOCOL_VIOLATION)
            if reply.status != ProbeTransportStatus.RECEIVED:
                if reply.payload is not None:
                    return ProbeTransportResult(ProbeTransportStatus.PROTOCOL_VIOLATION)
                return ProbeTransportResult(reply.status)
            if type(reply.payload) is not bytes:
                return ProbeTransportResult(ProbeTransportStatus.PROTOCOL_VIOLATION)
            if len(reply.payload) > MAX_PROTOCOL_MESSAGE_BYTES:
                return ProbeTransportResult(ProbeTransportStatus.BOUNDS_VIOLATION)
            with self._lock:
                if token.is_cancelled():
                    return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
                response = ingest_probe_response(
                    reply.payload,
                    session=self._session,
                    current_device_epoch=self._current_epoch(),
                    expected_request=request,
                )
                return ProbeTransportResult(ProbeTransportStatus.RECEIVED, response)
        except ProbeValidationError as exc:
            if token.is_cancelled():
                return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
            mapped = {
                ProbeErrorCode.BOUNDS_VIOLATION: ProbeTransportStatus.BOUNDS_VIOLATION,
                ProbeErrorCode.UNSUPPORTED_PROTOCOL: ProbeTransportStatus.UNSUPPORTED_PROTOCOL,
                ProbeErrorCode.EXPIRED: ProbeTransportStatus.TIMEOUT,
                ProbeErrorCode.SESSION_CLOSED: ProbeTransportStatus.CLOSED,
                ProbeErrorCode.REQUEST_PENDING: ProbeTransportStatus.BUSY,
            }.get(exc.code, ProbeTransportStatus.PROTOCOL_VIOLATION)
            return ProbeTransportResult(mapped)
        except TimeoutError:
            if token.is_cancelled():
                return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
            return ProbeTransportResult(ProbeTransportStatus.TIMEOUT)
        except ConnectionError:
            if token.is_cancelled():
                return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
            return ProbeTransportResult(ProbeTransportStatus.UNAVAILABLE)
        except Exception:
            # Last-resort fail-closed backstop (FG-13): any other adapter failure is ERROR
            # unless a cancellation already explains it. Deliberately never log or expose
            # str(exc), payloads or command details.
            if token.is_cancelled():
                return ProbeTransportResult(ProbeTransportStatus.CANCELLED)
            return ProbeTransportResult(ProbeTransportStatus.ERROR)
        finally:
            if claimed:
                self._session.finish_dispatch(request)
            with self._lock:
                self._busy = False

    def close(self) -> ProbeTransportStatus:
        with self._lock:
            if self._closed.is_set():
                return ProbeTransportStatus.CLOSED
            self._closed.set()
        self._session.close()
        try:
            self._cleanup()
        except Exception:
            # Adapter boundary (FG-13): concrete adapters raise their own typed failures;
            # any adapter fault, expected or not, is reported as ERROR (cleanup unverified)
            # and never swallowed. The details are deliberately not logged or exposed.
            return ProbeTransportStatus.ERROR
        return ProbeTransportStatus.CLOSED
