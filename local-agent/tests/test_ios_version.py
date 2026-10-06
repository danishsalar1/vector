"""Unit tests for AppleOSVersion semantic parsing and comparisons."""

from vector_agent.devices.ios.version import AppleOSVersion


class TestAppleOSVersionParsing:
    """Tests for parsing various Apple OS version string formats."""

    def test_parse_major_only(self) -> None:
        v = AppleOSVersion.parse("17")
        assert v is not None
        assert v.major == 17
        assert v.minor == 0
        assert v.patch == 0
        assert str(v) == "17.0"

    def test_parse_major_minor(self) -> None:
        v = AppleOSVersion.parse("17.4")
        assert v is not None
        assert v.major == 17
        assert v.minor == 4
        assert v.patch == 0
        assert str(v) == "17.4"

    def test_parse_major_minor_patch(self) -> None:
        v = AppleOSVersion.parse("17.4.1", build_version="21E236")
        assert v is not None
        assert v.major == 17
        assert v.minor == 4
        assert v.patch == 1
        assert v.build_version == "21E236"
        assert str(v) == "17.4.1"

    def test_parse_ios_27_fixtures(self) -> None:
        v = AppleOSVersion.parse("27.0.1", build_version="31A100")
        assert v is not None
        assert v.major == 27
        assert v.minor == 0
        assert v.patch == 1
        assert v.build_version == "31A100"

    def test_parse_empty_and_whitespace(self) -> None:
        assert AppleOSVersion.parse("") is None
        assert AppleOSVersion.parse(None) is None
        assert AppleOSVersion.parse("   ") is None

    def test_parse_malformed(self) -> None:
        assert AppleOSVersion.parse("invalid") is None
        assert AppleOSVersion.parse("v1.2.3") is None
        assert AppleOSVersion.parse("17.") is None
        assert AppleOSVersion.parse("17.4beta") is None
        assert AppleOSVersion.parse("17.4.1.2") is None
        assert AppleOSVersion.parse("foo") is None
        assert AppleOSVersion.parse("1e5") is None
        assert AppleOSVersion.parse("12 monkeys") is None
        assert AppleOSVersion.parse("18.6.2 (beta)") is None

    def test_parse_strict_valid(self) -> None:
        v = AppleOSVersion.parse("18.6.2")
        assert v is not None
        assert v.major == 18
        assert v.minor == 6
        assert v.patch == 2


class TestAppleOSVersionComparisons:
    """Tests for rich numeric comparisons without string comparison bugs."""

    def test_minor_comparison_bug_avoidance(self) -> None:
        # String comparison would say "17.10" < "17.4", which is WRONG.
        # Numeric comparison must say 17.10 > 17.4.
        v_17_10 = AppleOSVersion.parse("17.10")
        v_17_4 = AppleOSVersion.parse("17.4")
        assert v_17_10 is not None and v_17_4 is not None
        assert v_17_10 > v_17_4
        assert v_17_4 < v_17_10

        v_26_7_1 = AppleOSVersion.parse("26.7.1")
        v_27 = AppleOSVersion.parse("27")
        assert v_26_7_1 is not None and v_27 is not None
        assert v_26_7_1 < v_27

    def test_equality(self) -> None:
        v1 = AppleOSVersion.parse("18.0.0")
        v2 = AppleOSVersion.parse("18")
        assert v1 == v2
        assert hash(v1) == hash(v2)

        v_27_0_0 = AppleOSVersion.parse("27.0.0")
        v_27 = AppleOSVersion.parse("27")
        assert v_27_0_0 == v_27
        assert hash(v_27_0_0) == hash(v_27)

    def test_skipped_major_releases(self) -> None:
        v_18 = AppleOSVersion.parse("18.2")
        v_27 = AppleOSVersion.parse("27.0.0")
        assert v_18 is not None and v_27 is not None
        assert v_27 > v_18

    def test_is_at_least(self) -> None:
        v = AppleOSVersion.parse("17.4.1")
        assert v is not None
        assert v.is_at_least(17, 4)
        assert v.is_at_least(17, 4, 1)
        assert not v.is_at_least(17, 5)
        assert not v.is_at_least(18)

    def test_is_below(self) -> None:
        v = AppleOSVersion.parse("16.7.10")
        assert v is not None
        assert v.is_below(17)
        assert v.is_below(16, 8)
        assert not v.is_below(16, 7)

    def test_is_within(self) -> None:
        v = AppleOSVersion.parse("17.4.0")
        assert v is not None
        assert v.is_within(min_ver=(17, 0), max_ver=(17, 5))
        assert not v.is_within(min_ver=(17, 5))
        assert not v.is_within(max_ver=(17, 3))
