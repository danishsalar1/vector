"""Explicit operator tool: verify the controlled debug APK and enroll its digest.

Run as `python -m vector_agent.probe.trust_build --sdk-root ... --java ...
--expected-signer <SHA256>`. No install, signing, key generation or device command.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import re
from pathlib import Path

from vector_agent.devices.android.probe_bridge import PACKAGE, TrustedProbeArtifact
from vector_agent.security.bounded_process import capture

REPOSITORY = Path(__file__).resolve().parents[4]


def verify_build(sdk_root: Path, java: Path, expected_signer: str) -> TrustedProbeArtifact:
    if re.fullmatch(r"[0-9a-f]{64}", expected_signer) is None:
        raise ValueError("Expected signer must be a lowercase SHA-256 fingerprint.")
    build = REPOSITORY / "android-probe/app/build/outputs/apk/debug"
    apk = build / "app-debug.apk"
    if apk.resolve().parent != build.resolve() or apk.is_symlink() or not apk.is_file():
        raise ValueError("Controlled Probe build unavailable.")
    # Bound local build reads too, and compare before/after external verification.
    if apk.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Probe build exceeds the artifact budget.")
    with apk.open("rb") as stream:
        before = hashlib.file_digest(stream, "sha256").hexdigest()
    build_tools = sdk_root / "build-tools/35.0.0"
    signed = capture(
        [
            str(java),
            "-jar",
            str(build_tools / "lib/apksigner.jar"),
            "verify",
            "--verbose",
            "--print-certs",
            str(apk),
        ],
        timeout=30,
    )
    output = signed.stdout.decode("utf-8", errors="strict")
    signers = [
        match[1]
        for line in output.splitlines()
        if (
            match := re.fullmatch(
                r"Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-f]{64})", line
            )
        )
    ]
    if (
        signed.returncode
        or len(signers) != 1
        or not hmac.compare_digest(signers[0], expected_signer)
    ):
        raise ValueError("Probe signature verification failed.")
    metadata = capture([str(build_tools / "aapt2.exe"), "dump", "badging", str(apk)], timeout=30)
    text = metadata.stdout.decode("utf-8", errors="strict")
    if (
        metadata.returncode
        or re.search(
            r"^package: name='"
            + re.escape(PACKAGE)
            + r"' versionCode='1' versionName='0\.1\.0'(?: |$)",
            text,
            re.MULTILINE,
        )
        is None
        or "application-debuggable" not in text.splitlines()
    ):
        raise ValueError("Probe build metadata rejected.")
    with apk.open("rb") as stream:
        after = hashlib.file_digest(stream, "sha256").hexdigest()
    if not hmac.compare_digest(before, after):
        raise ValueError("Probe build changed during verification.")
    return TrustedProbeArtifact(apk_sha256=after, signer_sha256=expected_signer)


def load_trusted_artifact(path: Path) -> TrustedProbeArtifact | None:
    try:
        with path.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        return TrustedProbeArtifact.model_validate_json(raw, strict=True)
    except (OSError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--java", required=True, type=Path)
    parser.add_argument("--expected-signer", required=True)
    args = parser.parse_args()
    artifact = verify_build(args.sdk_root, args.java, args.expected_signer)
    destination = REPOSITORY / "local-agent/.data/probe-trust.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(artifact.model_dump_json(), encoding="utf-8")
    temporary.replace(destination)
    print("Verified development Probe build enrolled. Restart the local agent to use it.")


if __name__ == "__main__":
    main()
