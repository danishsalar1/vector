"""Semantic and numeric Apple OS version representation.

Invariants:
- Never compares versions as strings (e.g. avoids '17.10' < '17.4' string bugs).
- Handles arbitrary depth: major, minor, patch (e.g. '17', '17.4', '17.4.1', '27.0.1').
- Preserves raw string and BuildVersion separately.
- Malformed or unknown versions never raise exceptions; return None or UNKNOWN.
- Tolerates skipped major versions (e.g. iOS 18 to 26/27).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

_STRICT_VERSION_RE = re.compile(r"^(\d{1,4})(?:\.(\d{1,4}))?(?:\.(\d{1,4}))?\Z")


@total_ordering
@dataclass(frozen=True)
class AppleOSVersion:
    """Semantic Apple OS version with major, minor, patch components."""

    major: int
    minor: int = 0
    patch: int = 0
    raw_version: str = ""
    build_version: str | None = None

    @classmethod
    def parse(
        cls,
        version_str: str | None,
        build_version: str | None = None,
    ) -> AppleOSVersion | None:
        """Parse an Apple OS version string safely.

        Examples of valid inputs:
        - "17" -> 17.0.0
        - "17.4" -> 17.4.0
        - "17.4.1" -> 17.4.1
        - "18.6.2" -> 18.6.2
        - "27" -> 27.0.0
        - "27.0.1" -> 27.0.1

        Strictly rejects:
        - "17." (trailing dot)
        - "17.4beta" (non-numeric suffix)
        - "17.4.1.2" (too many components)
        - "foo", "1e5", "12 monkeys"
        - embedded whitespace or control characters

        Returns None if input is empty or cannot be parsed numerically.
        """
        if not version_str or not version_str.strip():
            return None

        cleaned = version_str.strip()
        if any(c in cleaned for c in "\r\n\0\t "):
            return None

        # Match exactly major(.minor(.patch)?)
        match = _STRICT_VERSION_RE.match(cleaned)
        if not match:
            return None

        try:
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) is not None else 0
            patch = int(match.group(3)) if match.group(3) is not None else 0
            return cls(
                major=major,
                minor=minor,
                patch=patch,
                raw_version=cleaned,
                build_version=build_version.strip() if build_version else None,
            )
        except (ValueError, TypeError, OverflowError):
            return None

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AppleOSVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, AppleOSVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def is_at_least(self, major: int, minor: int = 0, patch: int = 0) -> bool:
        """Return True if self is >= (major, minor, patch)."""
        return (self.major, self.minor, self.patch) >= (major, minor, patch)

    def is_below(self, major: int, minor: int = 0, patch: int = 0) -> bool:
        """Return True if self is < (major, minor, patch)."""
        return (self.major, self.minor, self.patch) < (major, minor, patch)

    def is_within(
        self,
        min_ver: tuple[int, ...] | None = None,
        max_ver: tuple[int, ...] | None = None,
    ) -> bool:
        """Return True if version falls inclusively within [min_ver, max_ver]."""
        self_tuple = (self.major, self.minor, self.patch)

        if min_ver is not None:
            norm_min = (
                min_ver[0],
                min_ver[1] if len(min_ver) > 1 else 0,
                min_ver[2] if len(min_ver) > 2 else 0,
            )
            if self_tuple < norm_min:
                return False

        if max_ver is not None:
            norm_max = (
                max_ver[0],
                max_ver[1] if len(max_ver) > 1 else 0,
                max_ver[2] if len(max_ver) > 2 else 0,
            )
            if self_tuple > norm_max:
                return False

        return True

    def __str__(self) -> str:
        if self.patch > 0:
            return f"{self.major}.{self.minor}.{self.patch}"
        return f"{self.major}.{self.minor}"
