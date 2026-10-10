"""VECTOR agent configuration.

All runtime parameters are centralized here.
Never scatter timeouts, ports, or paths throughout the codebase.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vector_agent.security.http_boundary import validate_allowed_origins, validate_trusted_hosts


class AgentSettings(BaseSettings):
    """Runtime configuration for the VECTOR local agent."""

    model_config = SettingsConfigDict(
        env_prefix="VECTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ---- Network ----
    host: str = "127.0.0.1"
    """Bind address.  Default is loopback – never expose to 0.0.0.0 without explicit config."""

    port: int = 8742
    """Local agent port. Chosen to avoid conflicts with common dev ports."""

    # ---- HTTP boundary (Host / Origin) ----
    trusted_hosts: list[str] = ["127.0.0.1", "localhost"]
    """Explicit Host allow-list (bare hostnames, no wildcard or port). Loopback only by default."""

    # ---- CORS / allowed Origins ----
    # Exact origins (no wildcard, no "null"): the Vite dev server (5173) and the
    # Vite preview server (4173). The same list authorizes the Origin header of
    # state-changing requests, including same-origin POSTs through the Vite proxy.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

    # ---- ADB ----
    adb_path: str = "adb"
    """Path to adb executable. Defaults to PATH lookup."""

    adb_timeout_seconds: float = 10.0
    """Timeout for a single ADB command."""

    adb_shell_timeout_seconds: float = 30.0
    """Timeout for longer ADB shell commands."""

    # ---- iOS tools ----
    ideviceinfo_path: str = "ideviceinfo"
    idevicediagnostics_path: str = "idevicediagnostics"
    idevicedevmodectl_path: str = "idevicedevmodectl"
    idevice_id_path: str = "idevice_id"
    idevicepair_path: str = "idevicepair"
    ios_timeout_seconds: float = 15.0

    # ---- Subprocess security ----
    subprocess_max_output_bytes: int = 512_000
    """Hard limit on subprocess stdout to prevent memory exhaustion."""

    # ---- Scan device presence (Stage 2B-3) ----
    presence_check_enabled: bool = True
    """Verify the scan's bound device is still attached before/after diagnostics."""

    presence_probe_timeout_seconds: float = 3.0
    """Timeout for ONE presence probe (a single bounded 'adb devices' / 'idevice_id -l')."""

    # ---- Scan ----
    scan_max_duration_seconds: float = 300.0
    """Maximum time a scan may run before forced cancellation."""

    diagnostic_default_timeout_seconds: float = 20.0

    # ---- Data ----
    data_dir: Path = Path(".data")
    """Local persistent data directory. Relative to cwd, never committed."""

    # ---- Demo mode ----
    demo_mode: bool = False
    """When True, the agent returns synthetic demo data. Never mix with real hardware."""

    # ---- Debug ----
    log_level: str = "INFO"
    log_raw_output: bool = False
    """If True, raw subprocess output is logged at DEBUG level. Redaction still applies."""

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v

    @field_validator("presence_probe_timeout_seconds")
    @classmethod
    def validate_presence_probe_timeout(cls, v: float) -> float:
        if not 0.5 <= v <= 10.0:
            raise ValueError("presence_probe_timeout_seconds must be between 0.5 and 10.")
        return v

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts_field(cls, v: list[str]) -> list[str]:
        return list(validate_trusted_hosts(v))

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins_field(cls, v: list[str]) -> list[str]:
        return list(validate_allowed_origins(v))

    @property
    def data_path(self) -> Path:
        return self.data_dir.resolve()


def get_settings() -> AgentSettings:
    """Return the singleton settings instance.

    Uses lru_cache semantics via module-level singleton.
    """
    return _settings


_settings: AgentSettings = AgentSettings()
