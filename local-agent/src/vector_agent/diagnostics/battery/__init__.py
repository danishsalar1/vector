"""Battery diagnostics package.

Exports the battery telemetry diagnostic and its definition constant.
"""

from vector_agent.diagnostics.battery.battery_diagnostic import (
    BATTERY_TELEMETRY_DEFINITION,
    BatteryTelemetryDiagnostic,
)

__all__ = [
    "BATTERY_TELEMETRY_DEFINITION",
    "BatteryTelemetryDiagnostic",
]
