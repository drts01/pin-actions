"""Tests for pin_actions._yaml_artifacts (yamlrocks blank-line-artifact workaround)."""

from pin_actions._yaml_artifacts import strip_blank_line_artifacts


class TestStripBlankLineArtifacts:
    """Test strip_blank_line_artifacts drops injected blanks but preserves real ones."""

    def test_artifact_before_sequence_item_removed(self) -> None:
        """A spurious blank line before a `- ` sequence item is stripped."""
        # Arrange
        original = b"steps:\n  - run: |\n      echo x\n  - run: echo y\n"
        rendered = b"steps:\n  - run: |\n      echo x\n  \n  - run: echo y\n"

        # Act
        result = strip_blank_line_artifacts(rendered, original)

        # Assert
        assert result == original

    def test_artifact_before_mapping_key_removed(self) -> None:
        """A spurious blank line before a sibling mapping key is stripped."""
        # Arrange
        original = b"a:\n  desc: |\n    line one\n  type: string\n"
        rendered = b"a:\n  desc: |\n    line one\n  \n  type: string\n"

        # Act
        result = strip_blank_line_artifacts(rendered, original)

        # Assert
        assert result == original

    def test_artifact_before_mapping_key_removed_nested(self) -> None:
        """A spurious blank line at a deeper nesting level is stripped."""
        # Arrange
        original = b"a:\n  b:\n    desc: |\n      x\n    z: 1\n"
        rendered = b"a:\n  b:\n    desc: |\n      x\n    \n    z: 1\n"

        # Act
        result = strip_blank_line_artifacts(rendered, original)

        # Assert
        assert result == original

    def test_preexisting_blank_line_before_key_preserved(self) -> None:
        """A blank line already present in the original at that position is kept."""
        # Arrange
        original = b"a: 1\n\nb: 2\n"
        rendered = b"a: 1\n\nb: 2\n"

        # Act
        result = strip_blank_line_artifacts(rendered, original)

        # Assert
        assert result == rendered

    def test_intentional_blank_line_inside_keep_chomp_content_preserved(self) -> None:
        """A blank line inside a `|+` block scalar's own content (followed by more content) is kept."""
        # Arrange
        original = b"run: |+\n  echo start\n\n  echo end\n"
        rendered = b"run: |+\n  echo start\n\n  echo end\n"

        # Act
        result = strip_blank_line_artifacts(rendered, original)

        # Assert
        assert result == rendered

    def test_no_artifact_no_change(self) -> None:
        """When rendered already matches original, nothing is stripped."""
        # Arrange
        original = b"a: 1\nb: 2\n"

        # Act
        result = strip_blank_line_artifacts(original, original)

        # Assert
        assert result == original

    def test_empty_input(self) -> None:
        """Empty rendered/original bytes round-trip without error."""
        # Arrange
        original = b""
        rendered = b""

        # Act
        result = strip_blank_line_artifacts(rendered, original)

        # Assert
        assert result == b""
