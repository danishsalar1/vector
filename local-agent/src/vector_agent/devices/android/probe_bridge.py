"""Fixed Android Probe operations. No arbitrary package/path/intent/forward API."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field, StringConstraints

from vector_agent.models.probe_lifecycle import ProbeAvailability as A
from vector_agent.models.probe_lifecycle import ProbeReason as R
from vector_agent.models.probe_lifecycle import ProbeState
from vector_agent.security.bounded_process import capture

# ruff: noqa: TID252
from ...models.probe import ProbeModel

PACKAGE = "org.vector.probe"
COMPONENT = PACKAGE + "/.ProbeActivity"
DIGEST = r"[0-9a-f]{64}"
Digest = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64)
]


class TrustedProbeArtifact(ProbeModel):
    """Trusted local build record, generated only after apksigner verification.

    This is operator configuration, NEVER peer-provided or an HTTP body. An exact
    APK hash pins its signed contents as well as its signer. It is not attestation.
    """

    apk_sha256: Digest
    signer_sha256: Digest
    application_version: str = "0.1.0"
    version_code: Annotated[int, Field(strict=True, ge=1)] = 1
    protocol_version: Annotated[int, Field(strict=True, ge=1)] = 1


@dataclass(frozen=True)
class ProbeBootstrap:
    key: bytes = field(repr=False)
    endpoint: str = field(repr=False)


class AndroidProbeBridge:
    def __init__(self, *, serial: str, adb_path: str = "adb") -> None:
        # Fullmatch deliberately does not inherit the legacy serial regex's $ behavior.
        if (
            type(serial) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}", serial) is None
        ):
            raise ValueError("Invalid device identifier.")
        self._serial = serial
        self._adb = adb_path  # trusted host configuration only
        self._ports: dict[int, str] = {}

    def _call(self, *args: str, limit: int = 65_536) -> tuple[int, str]:
        result = capture([self._adb, "-s", self._serial, *args], limit=limit)
        return result.returncode, result.stdout.decode("utf-8", errors="strict").strip()

    def discover(self, artifact: TrustedProbeArtifact | None) -> ProbeState:
        rc, packages = self._call("shell", "pm", "list", "packages", "--user", "0", PACKAGE)
        if rc:
            return ProbeState(availability=A.ERROR, reason=R.TOOL_ERROR)
        if f"package:{PACKAGE}" not in packages.splitlines():
            if packages:
                return ProbeState(availability=A.ERROR, reason=R.INVALID_RESPONSE)
            return ProbeState(
                availability=A.NOT_INSTALLED, reason=R.MANUAL_INSTALL_REQUIRED, installed=False
            )
        rc, disabled = self._call("shell", "pm", "list", "packages", "-d", "--user", "0", PACKAGE)
        if rc:
            return ProbeState(availability=A.ERROR, reason=R.TOOL_ERROR, installed=True)
        if f"package:{PACKAGE}" in disabled.splitlines():
            return ProbeState(availability=A.DISABLED, reason=R.PACKAGE_DISABLED, installed=True)
        if artifact is None:
            return ProbeState(
                availability=A.INSTALLED_UNVERIFIED,
                reason=R.TRUST_CONFIGURATION_REQUIRED,
                installed=True,
            )
        artifact = TrustedProbeArtifact.model_validate(artifact)
        rc, paths = self._call("shell", "pm", "path", "--user", "0", PACKAGE)
        # Single base APK only: no split packages or untrusted paths. Path only
        # flows from the fixed package query into this fixed hash operation.
        pattern = r"package:(/data/app/(?:~~[A-Za-z0-9_=-]+/)?org\.vector\.probe-[A-Za-z0-9_=-]+/base\.apk)"
        match = re.fullmatch(pattern, paths)
        if rc or match is None:
            return ProbeState(
                availability=A.INSTALLED_UNVERIFIED, reason=R.INVALID_RESPONSE, installed=True
            )
        rc, hashed = self._call("shell", "sha256sum", match[1])
        digest_match = re.fullmatch(r"(" + DIGEST + r")  " + re.escape(match[1]), hashed)
        if rc or digest_match is None:
            return ProbeState(
                availability=A.INSTALLED_UNVERIFIED, reason=R.INVALID_RESPONSE, installed=True
            )
        if not hmac.compare_digest(digest_match[1], artifact.apk_sha256):
            return ProbeState(
                availability=A.UNTRUSTED, reason=R.ARTIFACT_NOT_ALLOWLISTED, installed=True
            )
        compatible = (
            artifact.protocol_version,
            artifact.version_code,
            artifact.application_version,
        ) in (
            (1, 1, "0.1.0"),
            (2, 2, "0.2.0"),
        )
        return ProbeState(
            availability=A.INSTALLED_COMPATIBLE if compatible else A.INSTALLED_INCOMPATIBLE,
            reason=R.NONE if compatible else R.VERSION_NOT_SUPPORTED,
            installed=True,
            identity_trusted=True,
            protocol_compatible=compatible,
            application_version=artifact.application_version,
            protocol_version=artifact.protocol_version,
        )

    def launch(self) -> bool:
        rc, output = self._call("shell", "am", "start", "--user", "0", "-W", "-n", COMPONENT)
        return rc == 0 and "Status: ok" in output.splitlines()

    def stop(self) -> bool:
        rc, _ = self._call("shell", "am", "force-stop", "--user", "0", PACKAGE)
        return rc == 0

    def bootstrap(self) -> ProbeBootstrap | str:
        rc, output = self._call(
            "exec-out", "run-as", PACKAGE, "cat", "files/vector-probe-session", limit=1024
        )
        if rc:
            rc_test, _ = self._call("shell", "run-as", PACKAGE, "true", limit=256)
            if rc_test:
                return "RESTRICTED"
            return "NOT_STARTED"
        if output in ("REQUIRED", "DENIED", "EXPIRED"):
            return output
        match = re.fullmatch(r"([0-9a-f]{64})\n(vector_probe_[0-9a-f]{32})", output)
        if match is None:
            raise ValueError("Invalid Probe bootstrap.")
        return ProbeBootstrap(bytes.fromhex(match[1]), match[2])

    def forward(self, bootstrap: ProbeBootstrap) -> int:
        if re.fullmatch(r"vector_probe_[0-9a-f]{32}", bootstrap.endpoint) is None:
            raise ValueError("Invalid Probe endpoint.")
        rc, value = self._call(
            "forward", "tcp:0", "localabstract:" + bootstrap.endpoint, limit=1024
        )
        if rc or re.fullmatch(r"[0-9]{1,5}", value) is None or not 1024 <= int(value) <= 65535:
            raise ConnectionError("Probe forwarding unavailable.")
        port = int(value)
        self._ports[port] = bootstrap.endpoint
        return port

    def remove_forward(self, port: int) -> None:
        if port not in self._ports:
            raise ValueError("Forward is not owned by this Probe connection.")
        rc, listing = self._call("forward", "--list")
        expected = [self._serial, f"tcp:{port}", "localabstract:" + self._ports[port]]
        rows = [line.split() for line in listing.splitlines()]
        if rc or [row for row in rows if len(row) == 3 and row[1] == f"tcp:{port}"] != [expected]:
            raise ConnectionError("Probe forward ownership changed.")
        rc, _ = self._call("forward", "--remove", f"tcp:{port}", limit=1024)
        if rc:
            raise ConnectionError("Probe forwarding cleanup failed.")
        del self._ports[port]
