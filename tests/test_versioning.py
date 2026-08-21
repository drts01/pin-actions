"""Tests for semver/CalVer tag selection (property-based + example-based)."""

from hypothesis import given
from hypothesis import strategies as st
from pin_actions.versioning import parse_tag_version, select_latest_tags


class TestParseTagVersion:
    """Test tag parsing (semver/CalVer with dash normalization)."""

    def test_semver_vprefix(self) -> None:
        """Parse semver with 'v' prefix."""
        # Arrange, Act, Assert
        v = parse_tag_version("v1.2.3")
        assert v is not None
        assert v.release == (1, 2, 3)

    def test_semver_no_prefix(self) -> None:
        """Parse semver without prefix."""
        v = parse_tag_version("1.2.3")
        assert v is not None
        assert v.release == (1, 2, 3)

    def test_semver_prerelease(self) -> None:
        """Parse semver with prerelease suffix."""
        v = parse_tag_version("v1.2.3-rc1")
        assert v is not None
        assert v.release == (1, 2, 3)

    def test_calver_dot_separated(self) -> None:
        """Parse CalVer with dot separators."""
        v = parse_tag_version("2023.10.15")
        assert v is not None
        assert v.release == (2023, 10, 15)

    def test_calver_zero_padded(self) -> None:
        """Parse CalVer with zero-padded components."""
        v = parse_tag_version("2023.01.05")
        assert v is not None
        assert v.release == (2023, 1, 5)

    def test_calver_dash_separated(self) -> None:
        """Parse CalVer with dash separators (normalized to dots)."""
        v = parse_tag_version("2024-05-01")
        assert v is not None
        assert v.release == (2024, 5, 1)

    def test_calver_v_prefix_with_dash(self) -> None:
        """Parse CalVer with 'v' prefix and dashes."""
        v = parse_tag_version("v2024-05-01")
        assert v is not None
        assert v.release == (2024, 5, 1)

    def test_unparseable_branch_name(self) -> None:
        """Return None for branch names."""
        assert parse_tag_version("main") is None
        assert parse_tag_version("nightly") is None
        assert parse_tag_version("develop") is None

    def test_unparseable_dash_calver_fallback(self) -> None:
        """Return None for dash-separated tags that fail both direct and dash-fallback parsing."""
        # Covers line 25-26: dash normalization retry that also fails
        assert parse_tag_version("foo-bar-baz") is None  # non-numeric with dashes
        assert parse_tag_version("2024-a-b") is None  # mixed numeric/alpha with dashes

    @given(st.text(alphabet="0123456789.v", min_size=1, max_size=20))
    def test_property_valid_semver_parses(self, tag: str) -> None:
        """Property: semver-like strings parse without error."""
        # Should not raise
        parse_tag_version(tag)


class TestSelectLatestTags:
    """Test semver tag selection with constraints (returns sorted list, best first)."""

    def test_patch_constraint_downgrades_regression(self) -> None:
        """Patch constraint on major-only comment doesn't spuriously narrow to minor==0.

        Regression: v4 with --update patch should pick latest v4.x tag, not v4.0.x.
        """
        # Arrange
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.0", "sha_v4_9_0"),
            ("v5.1.0", "sha_v5_1_0"),
        ]

        # Act
        result = select_latest_tags(tags, "v4", latest_patch=True)

        # Assert
        assert result[0] == ("v4", "sha_v4_9_0")

    def test_patch_constraint_full_precision(self) -> None:
        """Patch constraint with full precision."""
        # Arrange
        tags = [
            ("v4.2.1", "sha_v4_2_1"),
            ("v4.2.9", "sha_v4_2_9"),
            ("v4.3.0", "sha_v4_3_0"),
        ]

        # Act
        result = select_latest_tags(tags, "v4.2.3", latest_patch=True)

        # Assert
        assert result[0] == ("v4.2.9", "sha_v4_2_9")

    def test_minor_constraint(self) -> None:
        """Minor constraint picks highest v4.x but not v5.x."""
        # Arrange
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.5", "sha_v4_9_5"),
            ("v5.0.0", "sha_v5_0_0"),
        ]

        # Act
        result = select_latest_tags(tags, "v4", latest_minor=True)

        # Assert
        assert result[0] == ("v4", "sha_v4_9_5")

    def test_major_constraint(self) -> None:
        """Major constraint picks globally highest tag."""
        # Arrange
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.5", "sha_v4_9_5"),
            ("v9.0.0", "sha_v9_0_0"),
        ]

        # Act
        result = select_latest_tags(tags, "v4", latest_major=True)

        # Assert
        assert result[0] == ("v9", "sha_v9_0_0")

    def test_full_version_flag(self) -> None:
        """With full_version=True, preserve full resolved tag precision."""
        # Arrange
        tags = [
            ("v4.0.1", "sha_v4_0_1"),
            ("v4.9.2", "sha_v4_9_2"),
            ("v5.0.0", "sha_v5_0_0"),
        ]

        # Act: without full_version
        result = select_latest_tags(tags, "v4", latest_minor=True, full_version=False)
        assert result[0] == ("v4", "sha_v4_9_2")

        # Act: with full_version
        result = select_latest_tags(tags, "v4", latest_minor=True, full_version=True)
        assert result[0] == ("v4.9.2", "sha_v4_9_2")

    def test_calver_dot_separated(self) -> None:
        """CalVer with dot separators."""
        # Arrange
        tags = [
            ("2023.01.05", "sha_2023_01_05"),
            ("2023.09.30", "sha_2023_09_30"),
            ("2024.01.02", "sha_2024_01_02"),
        ]

        # Act
        result = select_latest_tags(tags, "2023.01.05", latest_major=True)

        # Assert
        assert result[0] == ("2024.1.2", "sha_2024_01_02")

    def test_calver_dash_separated(self) -> None:
        """CalVer with dash separators."""
        # Arrange
        tags = [
            ("2024-01-05", "sha_2024_01_05"),
            ("2024-09-30", "sha_2024_09_30"),
            ("2025-01-02", "sha_2025_01_02"),
        ]

        # Act
        result = select_latest_tags(tags, "2024-01-05", latest_minor=True)

        # Assert
        assert result[0] == ("2024.9.30", "sha_2024_09_30")

    def test_calver_patch_constraint(self) -> None:
        """CalVer with patch constraint."""
        # Arrange
        tags = [
            ("2024.05.01", "sha_2024_05_01"),
            ("2024.05.15", "sha_2024_05_15"),
            ("2024.06.01", "sha_2024_06_01"),
        ]

        # Act
        result = select_latest_tags(tags, "2024.05.05", latest_patch=True)

        # Assert
        assert result[0] == ("2024.5.15", "sha_2024_05_15")

    def test_no_constraint(self) -> None:
        """Return empty list if no constraint is set."""
        # Arrange
        tags = [("v1.0.0", "sha")]

        # Act
        result = select_latest_tags(tags, "v1.0.0")

        # Assert
        assert result == []

    def test_unparseable_current_tag(self) -> None:
        """Return empty list if current_tag isn't a valid version."""
        # Arrange
        tags = [("v1.0.0", "sha")]

        # Act
        result = select_latest_tags(tags, "main", latest_major=True)

        # Assert
        assert result == []

    @given(
        st.lists(
            st.tuples(
                st.text(alphabet="v0123456789.", min_size=1, max_size=20),
                st.text(alphabet="abcdef0123456789", min_size=40, max_size=40),
            ),
            min_size=1,
            max_size=10,
            unique_by=lambda x: x[0],
        ),
    )
    def test_property_select_latest_never_crashes(self, tags: list[tuple[str, str]]) -> None:
        """Property: select_latest_tags never crashes on arbitrary tag inputs."""
        # Should not raise
        select_latest_tags(tags, "v1.0.0", latest_major=True)
        select_latest_tags(tags, "v1.0.0", latest_minor=True)
        select_latest_tags(tags, "v1.0.0", latest_patch=True)

    @given(
        st.lists(
            st.tuples(
                st.text(alphabet="v0123456789.", min_size=1, max_size=20),
                st.text(alphabet="abcdef0123456789", min_size=40, max_size=40),
            ),
            min_size=1,
            max_size=10,
            unique_by=lambda x: x[0],
        ),
    )
    def test_property_sorted_descending_and_satisfies_constraint(self, tags: list[tuple[str, str]]) -> None:
        """Property: results are sorted descending by version and satisfy the constraint."""
        current_tag = "v1.0.0"
        current = parse_tag_version(current_tag)

        for kwargs in (
            {"latest_major": True},
            {"latest_minor": True},
            {"latest_patch": True},
        ):
            result = select_latest_tags(tags, current_tag, **kwargs)

            # Invariant 1: sorted descending by version
            versions = [parse_tag_version(name) for name, _sha in result]
            assert versions == sorted(versions, reverse=True)

            # Invariant 2: every candidate satisfies the requested constraint
            if not kwargs.get("latest_major"):
                for version in versions:
                    assert version.major == current.major
