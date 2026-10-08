"""Length-prefixed, HMAC authenticated control frames over an owned ADB forward."""

from __future__ import annotations

import hashlib
import hmac
import socket
import struct
import threading
import time
from collections.abc import Callable
from contextlib import suppress

from vector_agent.devices.android.probe_bridge import AndroidProbeBridge, ProbeBootstrap
from vector_agent.models.probe import MAX_PROTOCOL_MESSAGE_BYTES, ProbeRequestEnvelope
from vector_agent.probe.protocol import ProbeProtocolSession
from vector_agent.probe.transport import (
    ProbeTransportStatus as T,
)

# ruff: noqa: TID252
from .transport import (
    ProbeCancellation,
    ProbeTransport,
    ProbeTransportReply,
)


class AdbProbeTransport(ProbeTransport):
    """Key is obtained from the verified development app's private run-as file.

    Direction-separated MACs cover the complete Phase 8A envelope. Nonce/session/
    epoch/sequence validation remains entirely in Phase 8A. A failed exchange
    requires lifecycle teardown; a connection is never implicitly re-established.
    """

    def __init__(
        self,
        *,
        session: ProbeProtocolSession,
        current_device_epoch: Callable[[], int],
        bridge: AndroidProbeBridge,
        bootstrap: ProbeBootstrap,
    ) -> None:
        super().__init__(session=session, current_device_epoch=current_device_epoch)
        if len(bootstrap.key) != 32:
            raise ValueError("Invalid Probe credential.")
        self._key = bootstrap.key
        self.cleanup_failed = False
        self._bridge = bridge
        self._io_lock = threading.Lock()
        self._socket: socket.socket | None = None
        self._port = bridge.forward(bootstrap)
        try:
            self._socket = socket.create_connection(("127.0.0.1", self._port), timeout=3)
        except OSError:
            bridge.remove_forward(self._port)
            self._key = b""
            raise ConnectionError("Probe endpoint unavailable.") from None

    def _exchange(
        self, request: ProbeRequestEnvelope, *, deadline: float, cancellation: ProbeCancellation
    ) -> ProbeTransportReply:
        with self._io_lock:
            sock = self._socket
            key = self._key
        if sock is None:
            return ProbeTransportReply(T.CLOSED)
        payload = request.model_dump_json().encode("utf-8")
        frame = (
            struct.pack("!I", len(payload))
            + hmac.digest(key, b"request\0" + payload, "sha256")
            + payload
        )

        class _CancelledError(Exception):
            pass

        def budget() -> float:
            remaining = deadline - time.monotonic()
            if cancellation.is_cancelled():
                raise _CancelledError
            if remaining <= 0:
                raise TimeoutError
            return min(remaining, 0.1)

        def read(size: int) -> bytes:
            data = bytearray()
            while len(data) < size:
                sock.settimeout(budget())
                try:
                    block = sock.recv(min(4096, size - len(data)))
                except TimeoutError:
                    continue
                if not block:
                    raise ConnectionError
                data.extend(block)
            return bytes(data)

        try:
            view = memoryview(frame)
            while view:
                sock.settimeout(budget())
                try:
                    sent = sock.send(view)
                except TimeoutError:
                    continue
                if sent == 0:
                    raise ConnectionError
                view = view[sent:]

            length = struct.unpack("!I", read(4))[0]
            if not 0 < length <= MAX_PROTOCOL_MESSAGE_BYTES:
                return ProbeTransportReply(T.BOUNDS_VIOLATION)
            mac, raw = read(32), read(length)
            if not hmac.compare_digest(
                mac, hmac.new(key, b"response\0" + raw, hashlib.sha256).digest()
            ):
                return ProbeTransportReply(T.AUTHENTICATION_FAILURE)
            return ProbeTransportReply(T.RECEIVED, raw)
        except _CancelledError:
            return ProbeTransportReply(T.CANCELLED)

    def _cleanup(self) -> None:
        with self._io_lock:
            sock, self._socket = self._socket, None
            self._key = b""
        if sock is not None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        try:
            self._bridge.remove_forward(self._port)
        except Exception:
            self.cleanup_failed = True
            raise ConnectionError("Probe forward cleanup failed.") from None
