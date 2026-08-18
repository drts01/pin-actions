"""Tests for CLI main() entrypoint (exit codes, stdout/stderr)."""

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pin_actions.config import Settings
from pin_actions.core import main
from pin_actions.errors import InvalidRefError, YAMLParseError

if TYPE_CHECKING:
    from pathlib import Path


class TestMainSuccess:
    """Test main() on successful run."""

    def test_prints_pinned_files(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Print list of modified files on success."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)
        workflow = workflows_dir / "ci.yml"
        workflow.write_text("name: Test\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n")

        # Mock sys.argv for CLI parsing
        test_args = ["pin-actions", "--path", str(workflows_dir), "--dry-run"]

        async def mock_run(_settings) -> list[Path]:
            return [workflow]

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()

        # Assert
        captured = capsys.readouterr()
        assert "Pinned 1 file(s):" in captured.out
        assert str(workflow) in captured.out

    def test_prints_no_files_modified(self, capsys: pytest.CaptureFixture) -> None:
        """Print 'No files modified' when nothing changed."""
        # Arrange
        test_args = ["pin-actions"]

        async def mock_run(_settings) -> list[Path]:
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()

        # Assert
        captured = capsys.readouterr()
        assert "No files modified" in captured.out


class TestMainErrors:
    """Test main() error handling and exit codes."""

    def test_pin_actions_error_exit_1(self, capsys: pytest.CaptureFixture) -> None:
        """Exit with code 1 on PinActionsError."""
        # Arrange
        test_args = ["pin-actions"]
        error = InvalidRefError("owner/repo", "nonexistent")

        async def mock_run(_settings) -> list[Path]:
            raise error

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    def test_exception_group_exit_1(self, capsys: pytest.CaptureFixture) -> None:
        """Exit with code 1 on ExceptionGroup."""
        # Arrange
        test_args = ["pin-actions"]
        error = YAMLParseError("/path/to/file.yml", "invalid syntax")
        exc_group = ExceptionGroup("1 file(s) failed to process", [error])

        async def mock_run(_settings) -> list[Path]:
            raise exc_group

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    def test_value_error_exit_1(self, capsys: pytest.CaptureFixture) -> None:
        """Exit with code 1 on ValueError."""
        # Arrange
        test_args = ["pin-actions", "--path", "/nonexistent/path"]

        async def mock_run(_settings) -> list[Path]:
            msg = "Path does not exist: /nonexistent/path"
            raise ValueError(msg)

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err


class TestMainVerbosity:
    """Test main() verbosity flag handling."""

    def test_verbose_flag_short(self, tmp_path: Path) -> None:
        """Short -v flag works for verbosity."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        test_args = ["pin-actions", "--path", str(workflows_dir), "-v", "2"]

        async def mock_run(settings) -> list[Path]:
            assert settings.verbose == 2
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()

    def test_verbose_flag_long(self, tmp_path: Path) -> None:
        """Long --verbose flag works for verbosity."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        test_args = ["pin-actions", "--path", str(workflows_dir), "--verbose", "1"]

        async def mock_run(settings) -> list[Path]:
            assert settings.verbose == 1
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()


class TestMainDryRun:
    """Test main() dry-run flag."""

    def test_dry_run_flag(self, tmp_path: Path) -> None:
        """--dry-run flag prevents file writes."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        test_args = ["pin-actions", "--path", str(workflows_dir), "--dry-run"]

        async def mock_run(settings) -> list[Path]:
            assert settings.dry_run is True
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()


class TestMainUpdateFlag:
    """Test main() update strategy flag."""

    def test_update_major_flag(self, tmp_path: Path) -> None:
        """--update major flag."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        test_args = ["pin-actions", "--path", str(workflows_dir), "--update", "major"]

        async def mock_run(settings) -> list[Path]:
            assert settings.update == "major"
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()

    def test_update_minor_flag(self, tmp_path: Path) -> None:
        """--update minor flag."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        test_args = ["pin-actions", "--path", str(workflows_dir), "--update", "minor"]

        async def mock_run(settings) -> list[Path]:
            assert settings.update == "minor"
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()

    def test_update_patch_flag(self, tmp_path: Path) -> None:
        """--update patch flag."""
        # Arrange
        workflows_dir = tmp_path / ".github" / "workflows"
        workflows_dir.mkdir(parents=True)

        test_args = ["pin-actions", "--path", str(workflows_dir), "--update", "patch"]

        async def mock_run(settings) -> list[Path]:
            assert settings.update == "patch"
            return []

        # Act
        with (
            patch("sys.argv", test_args),
            patch("pin_actions.core.run", side_effect=mock_run),
        ):
            main()


class TestHelpFlagDrift:
    """Guard against --help output drifting from Settings fields."""

    def test_help_lists_every_settings_flag(self, capsys: pytest.CaptureFixture) -> None:
        """Every Settings field's primary kebab-case flag appears in --help output."""
        # Arrange
        test_args = ["pin-actions", "--help"]

        # Act
        with patch("sys.argv", test_args), pytest.raises(SystemExit):
            main()

        # Assert
        help_text = capsys.readouterr().out
        for field_name in Settings.model_fields:
            flag = f"--{field_name.replace('_', '-')}"
            assert flag in help_text, f"Settings field {field_name!r} missing from --help output as {flag!r}"
