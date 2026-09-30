"""Fuzzy membership function definitions.

These define how crisp diagnostic values map to linguistic degrees.

For a diagnostic signal x in [0, 1]:
- LOW term:    high membership near 0
- MEDIUM term: high membership near 0.5
- HIGH term:   high membership near 1.0
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

MF = Callable[[float], float]


@dataclass
class TriangularMF:
    """Triangular membership function parameterized by (a, b, c).

    Invariant: a <= b <= c.
    The genome repair function enforces this after mutation.
    """

    a: float  # Left foot
    b: float  # Peak
    c: float  # Right foot

    def __call__(self, x: float) -> float:
        a, b, c = self.a, self.b, self.c
        if b == a and b == c:
            return 1.0 if x == b else 0.0
        left = (x - a) / (b - a) if b != a else (0.0 if x < b else 1.0)
        right = (c - x) / (c - b) if c != b else (0.0 if x > c else 1.0)
        return float(np.clip(min(left, right), 0.0, 1.0))


def default_three_term_mfs(lo: float = 0.0, hi: float = 1.0) -> list[TriangularMF]:
    """Return [LOW, MEDIUM, HIGH] triangular MFs spanning [lo, hi].

    Used as initialization before evolutionary optimization.
    """
    mid = (lo + hi) / 2.0
    return [
        TriangularMF(a=lo, b=lo, c=mid),  # LOW
        TriangularMF(a=lo, b=mid, c=hi),  # MEDIUM
        TriangularMF(a=mid, b=hi, c=hi),  # HIGH
    ]
