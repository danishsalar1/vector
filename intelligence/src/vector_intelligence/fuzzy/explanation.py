"""Trust score explanation generator.

Produces human-readable explanations of why a Trust Score was assigned.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrustExplanation:
    """Structured explanation of a Trust Score."""

    trust_score: float
    confidence: float
    positive_factors: list[str]
    negative_factors: list[str]
    restricted_factors: list[str]
    unsupported_factors: list[str]

    def to_text(self) -> str:
        lines = [
            f"VECTOR Trust Score: {self.trust_score:.0%}",
            f"Confidence: {self.confidence:.0%}",
            "",
        ]
        if self.positive_factors:
            lines.append("Positive indicators:")
            lines.extend(f"  + {f}" for f in self.positive_factors)
        if self.negative_factors:
            lines.append("Negative indicators:")
            lines.extend(f"  - {f}" for f in self.negative_factors)
        if self.restricted_factors:
            lines.append("Restricted (OS limitation):")
            lines.extend(f"  ? {f}" for f in self.restricted_factors)
        if self.unsupported_factors:
            lines.append("Not applicable for this device:")
            lines.extend(f"  ~ {f}" for f in self.unsupported_factors)
        return "\n".join(lines)
