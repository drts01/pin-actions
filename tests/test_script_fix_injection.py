"""Tests for scripts/fix_injection.py (GHA script-injection remediation)."""

import subprocess
import sys
from pathlib import Path


import pytest
import yamlrocks


sys.path.insert(0, str(Path(__file__).parent))
from scripts.fix_injection import InjectionSettings, fix_injection_file

from pin_actions.errors import YAMLParseError


class TestInjectionDefaults:
    """Test InjectionSettings defaults."""

    def test_default_paths(self) -> None:
        """Default paths match pin-actions' workflow/action discovery."""
        assert InjectionSettings().paths == [
            Path(".github/workflows"),
            Path("**/action.yml"),
            Path("**/action.yaml"),
        ]


class TestFixInjectionFile:
    """Test fix_injection_file detecting and remediating untrusted ${{ }} in run: steps."""

    def test_untrusted_expr_hoisted_to_env(self, tmp_path: Path) -> None:
        """Untrusted issue.title interpolated in run: is hoisted to env: and $VAR."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            'jobs:\n  build:\n    steps:\n      - run: echo "Title was ${{ github.event.issue.title }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed
        content = wf.read_text()
        run_line, env_block = content.split("env:")
        assert "${{" not in run_line
        assert "${{ github.event.issue.title }}" in env_block

    def test_trusted_expr_left_untouched(self, tmp_path: Path) -> None:
        """Trusted context (github.repository) is not rewritten."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = 'jobs:\n  build:\n    steps:\n      - run: echo "${{ github.repository }}"\n'
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert wf.read_text() == original

    def test_pwsh_shell_uses_env_syntax(self, tmp_path: Path) -> None:
        """pwsh steps get $env:VAR placeholder syntax, not $VAR."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - shell: pwsh\n"
            '        run: Write-Output "${{ github.event.issue.title }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert "$env:" in content

    def test_unknown_shell_report_only(self, tmp_path: Path) -> None:
        """An unrecognized shell is left untouched; finding is report-only."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = (
            'jobs:\n  build:\n    steps:\n      - shell: fish\n        run: echo "${{ github.event.issue.title }}"\n'
        )
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert len(findings) == 1
        assert not findings[0].fixed
        assert wf.read_text() == original

    def test_function_wrapped_expr_report_only(self, tmp_path: Path) -> None:
        """fromJSON(...)-wrapped untrusted context is reported but not auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = "jobs:\n  build:\n    steps:\n      - run: echo '${{ fromJSON(github.event.issue.title) }}'\n"
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert len(findings) == 1
        assert not findings[0].fixed
        assert wf.read_text() == original

    def test_dry_run_no_write(self, tmp_path: Path) -> None:
        """Don't write file in dry_run mode, even though findings/modified are reported."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = 'jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.issue.title }}"\n'
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=True)

        # Assert
        assert modified
        assert findings[0].fixed
        assert wf.read_text() == original

    def test_idempotent_second_run_no_further_changes(self, tmp_path: Path) -> None:
        """Running twice produces no further changes after the first fix."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text('jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.issue.title }}"\n')

        # Act
        fix_injection_file(wf, dry_run=False)
        modified_again, findings_again, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified_again
        assert findings_again == []

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        """Raise YAMLParseError on malformed YAML."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text("jobs:\n  build: [\n")

        # Act, Assert
        with pytest.raises(YAMLParseError, match="Failed to parse YAML"):
            fix_injection_file(wf, dry_run=False)

    def test_dedup_repeated_expr_same_var(self, tmp_path: Path) -> None:
        """The same untrusted expression repeated in one step reuses a single env var."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            '      - run: echo "${{ github.event.issue.title }}" "${{ github.event.issue.title }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        content = wf.read_text()
        assert content.count("github.event.issue.title") == 1


class TestTrustedExprHoistedAlongsideUntrusted:
    """CodeQL's code-injection sink is the whole run: script: a residual trusted ${{ }}
    left inline once any untrusted expr is hoisted can still anchor a reported finding
    (e.g. github.repository), so every plain expression in a rewritten step is hoisted.
    """

    def test_trusted_expr_hoisted_but_not_reported_as_fixed(self, tmp_path: Path) -> None:
        """github.repository alongside an untrusted expr is hoisted to env:, without its own finding."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            '      - run: echo "${{ github.event.issue.title }}" "${{ github.repository }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert [f.expr for f in findings] == ["github.event.issue.title"]
        content = wf.read_text()
        run_line, env_block = content.split("env:")
        assert "${{" not in run_line
        assert "${{ github.event.issue.title }}" in env_block
        assert "${{ github.repository }}" in env_block

    def test_solo_trusted_expr_still_left_untouched(self, tmp_path: Path) -> None:
        """A step with only a trusted expr (no untrusted sibling) is not rewritten at all."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = 'jobs:\n  build:\n    steps:\n      - run: echo "${{ github.repository }}"\n'
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert wf.read_text() == original

    def test_idempotent_second_run_after_mixed_hoist(self, tmp_path: Path) -> None:
        """Running twice on a step mixing untrusted + trusted exprs produces no further changes."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            '      - run: echo "${{ github.event.issue.title }}" "${{ github.repository }}"\n',
        )

        # Act
        fix_injection_file(wf, dry_run=False)
        modified_again, findings_again, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified_again
        assert findings_again == []


class TestExpandedUntrustedContexts:
    """Test newly-added untrusted context prefixes (inputs, client_payload, event fields)."""

    def test_workflow_dispatch_input_fixed(self, tmp_path: Path) -> None:
        """github.event.inputs.* (workflow_dispatch/workflow_call) is auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            'jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.inputs.target }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    def test_bare_inputs_fixed(self, tmp_path: Path) -> None:
        """Bare inputs.* (composite action inputs, top-level workflow_call inputs) is auto-fixed."""
        # Arrange
        wf = tmp_path / "action.yml"
        wf.write_text(
            'runs:\n  steps:\n    - run: echo "${{ inputs.username }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    def test_repository_dispatch_client_payload_fixed(self, tmp_path: Path) -> None:
        """github.event.client_payload.* (repository_dispatch) is auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            'jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.client_payload.cmd }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    def test_release_body_fixed(self, tmp_path: Path) -> None:
        """github.event.release.body is auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            'jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.release.body }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    def test_still_trusted_fields_untouched(self, tmp_path: Path) -> None:
        """Trusted numeric/identity fields adjacent to newly-added prefixes stay untouched."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = (
            "jobs:\n  build:\n    steps:\n"
            '      - run: echo "${{ github.event.pull_request.number }} ${{ github.repository }}"\n'
        )
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert wf.read_text() == original


class TestBlockScalarPreservation:
    """Test that literal/folded run: block scalars keep real newlines, not \\n escapes."""

    def test_literal_block_keeps_real_newlines(self, tmp_path: Path) -> None:
        """A `run: |` step's untrusted expr is fixed without collapsing to a \\n-escaped scalar."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: |\n"
            "          echo start\n"
            '          echo "Title was ${{ github.event.issue.title }}"\n'
            "          echo end\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert "\\n" not in content
        assert "run: |\n" in content
        assert "          echo start\n" in content
        assert "          echo end\n" in content
        assert "env:" in content

    def test_folded_block_keeps_style(self, tmp_path: Path) -> None:
        """A `run: >` (folded) step is fixed while keeping folded style, not escaped."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: >\n"
            "          echo start\n"
            "          echo Title was ${{ github.event.issue.title }}\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert "\\n" not in content
        assert "run: >\n" in content

    def test_literal_block_strip_chomping_preserved(self, tmp_path: Path) -> None:
        """A `run: |-` (strip chomping, no trailing newline) step keeps the `-` indicator."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: |-\n"
            "          echo start\n"
            "          echo Title was ${{ github.event.issue.title }}\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert "\\n" not in content
        assert "run: |-\n" in content

    def test_literal_block_with_blank_line_in_content_no_trailing_whitespace(self, tmp_path: Path) -> None:
        """A blank line inside the run: block content isn't re-indented into trailing whitespace."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: |\n"
            "          echo start\n"
            "          echo Title was ${{ github.event.issue.title }}\n"
            "\n"
            "          echo end\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert not any(line != line.rstrip() for line in content.split("\n"))
        assert "\n\n          echo end\n" in content

    def test_literal_block_keep_chomp_trailing_blank_lines_no_trailing_whitespace(self, tmp_path: Path) -> None:
        """Keep-chomp (`|+`) trailing blank lines aren't re-indented into trailing whitespace."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: |+\n"
            "          echo start\n"
            "          echo Title was ${{ github.event.issue.title }}\n"
            "\n"
            "\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert not any(line != line.rstrip() for line in content.split("\n"))

    def test_literal_block_preceding_sibling_step_keeps_blank_line_count(self, tmp_path: Path) -> None:
        """Fixing one step doesn't inject a spurious blank line after an earlier, untouched
        literal-block step that abuts the next sequence item (yamlrocks round-trip quirk).
        """
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: |\n"
            "          echo start\n"
            "          echo end\n"
            "      - run: |\n"
            "          echo Title was ${{ github.event.issue.title }}\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert not any(line.strip() == "" and line != "" for line in content.split("\n"))
        assert "      - run: |\n          echo start\n          echo end\n      - run: |\n" in content

    def test_literal_block_idempotent_second_run(self, tmp_path: Path) -> None:
        """Running the fixer twice on a literal-block run: step produces no further changes."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: |\n"
            "          echo start\n"
            '          echo "Title was ${{ github.event.issue.title }}"\n'
            "          echo end\n",
        )

        # Act
        fix_injection_file(wf, dry_run=False)
        modified_again, findings_again, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified_again
        assert findings_again == []

    def test_single_line_run_unaffected_by_splice_logic(self, tmp_path: Path) -> None:
        """A plain single-line run: step (no block scalar) is fixed exactly as before."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text('jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.issue.title }}"\n')

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        assert "\\n" not in content


class TestQuoting:
    """Test that hoisted $VAR/$env:VAR references are requoted to preserve semantics."""

    def test_bare_unquoted_expr_wrapped_in_double_quotes(self, tmp_path: Path) -> None:
        """An unquoted ${{ }} in run: is hoisted to a double-quoted $VAR, not a bare one."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text("jobs:\n  build:\n    steps:\n      - run: echo ${{ github.event.issue.title }}\n")

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        run_value = yamlrocks.load(wf, option=yamlrocks.OPT_ROUND_TRIP)["jobs"]["build"]["steps"][0]["run"]
        assert run_value == 'echo "$GITHUB_EVENT_ISSUE_TITLE"'

    def test_already_double_quoted_expr_not_double_wrapped(self, tmp_path: Path) -> None:
        """An already double-quoted ${{ }} keeps single-level double quotes after hoisting."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text('jobs:\n  build:\n    steps:\n      - run: echo "${{ github.event.issue.title }}"\n')

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        run_value = yamlrocks.load(wf, option=yamlrocks.OPT_ROUND_TRIP)["jobs"]["build"]["steps"][0]["run"]
        assert run_value == 'echo "$GITHUB_EVENT_ISSUE_TITLE"'

    def test_single_quoted_expr_spliced_to_preserve_expansion(self, tmp_path: Path) -> None:
        """An ${{ }} inside a single-quoted string is spliced out so $VAR still expands."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: \"echo 'Title: ${{ github.event.issue.title }}'\"\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        run_line = yamlrocks.load(wf, option=yamlrocks.OPT_ROUND_TRIP)["jobs"]["build"]["steps"][0]["run"]
        assert run_line == "echo 'Title: '\"$GITHUB_EVENT_ISSUE_TITLE\"''"

        # bash -n confirms the rewritten line is syntactically valid shell.
        result = subprocess.run(["bash", "-n", "-c", run_line], capture_output=True, check=False)  # noqa: S603, S607

        assert result.returncode == 0, result.stderr.decode()

        # And functionally, $GITHUB_EVENT_ISSUE_TITLE still expands (unlike if left inside single quotes).
        result = subprocess.run(  # noqa: S603
            ["bash", "-c", run_line],  # noqa: S607
            capture_output=True,
            check=False,
            env={"GITHUB_EVENT_ISSUE_TITLE": "hello world", "PATH": "/usr/bin:/bin"},
        )
        assert result.stdout.decode() == "Title: hello world\n"

    def test_mixed_quoted_and_unquoted_exprs_same_line(self, tmp_path: Path) -> None:
        """Two untrusted exprs on one line, one bare and one double-quoted, are each handled correctly."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            '      - run: echo ${{ github.event.issue.title }} "${{ github.event.issue.body }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 2
        content = wf.read_text()
        run_line = content.splitlines()[3].split("run: ", 1)[1]
        assert run_line == 'echo "$GITHUB_EVENT_ISSUE_TITLE" "$GITHUB_EVENT_ISSUE_BODY"'

    def test_pwsh_bare_expr_wrapped_in_double_quotes(self, tmp_path: Path) -> None:
        """pwsh steps also wrap a bare $env:VAR reference in double quotes."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - shell: pwsh\n"
            "        run: Write-Output ${{ github.event.issue.title }}\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        content = wf.read_text()
        run_line = content.splitlines()[4]
        assert run_line.strip() == 'run: Write-Output "$env:GITHUB_EVENT_ISSUE_TITLE"'

    def test_pwsh_single_quoted_expr_spliced_with_plus(self, tmp_path: Path) -> None:
        """pwsh single-quoted ${{ }} is spliced using '+' concatenation, not bash-style adjacency."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - shell: pwsh\n"
            "        run: \"Write-Output 'Title: ${{ github.event.issue.title }}'\"\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        run_line = yamlrocks.load(wf, option=yamlrocks.OPT_ROUND_TRIP)["jobs"]["build"]["steps"][0]["run"]
        assert run_line.strip() == "Write-Output 'Title: '+\"$env:GITHUB_EVENT_ISSUE_TITLE\"+''"

    def test_cmd_single_quote_left_unchanged(self, tmp_path: Path) -> None:
        """cmd's %VAR% expands regardless of quoting, so no quote-splicing is attempted."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - shell: cmd\n"
            "        run: \"echo 'Title: ${{ github.event.issue.title }}'\"\n",
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings[0].fixed
        run_line = yamlrocks.load(wf, option=yamlrocks.OPT_ROUND_TRIP)["jobs"]["build"]["steps"][0]["run"]
        assert run_line.strip() == "echo 'Title: %GITHUB_EVENT_ISSUE_TITLE%'"

    def test_requoting_idempotent_second_run(self, tmp_path: Path) -> None:
        """Running the fixer twice on a requoted step produces no further changes."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: \"echo 'Title: ${{ github.event.issue.title }}'\"\n",
        )

        # Act
        fix_injection_file(wf, dry_run=False)
        modified_again, findings_again, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified_again
        assert findings_again == []


class TestNewUntrustedContexts:
    """Test additional untrusted leaf/whole-object contexts from CodeQL's data model."""

    @pytest.mark.parametrize(
        "expr",
        [
            "github.event.workflow_run.head_commit.message",
            "github.event.workflow_run.head_commit.author.email",
            "github.event.workflow_run.head_commit.committer.name",
            "github.event.workflow_run.head_repository.description",
            "github.event.workflow_run.pull_requests",
            "github.event.merge_group.head_ref",
            "github.event.merge_group.committer.email",
            "github.event.pull_request.head.repo.homepage",
            "github.event.pull_request.head.repo.description",
            "github.event.head_commit.committer.email",
            "github.event.changes",
            "github.event.workflow.path",
            "github.event.workflow_run.path",
            "github.event.workflow_run.referenced_workflows.path",
        ],
    )
    def test_new_leaf_context_fixed(self, tmp_path: Path, expr: str) -> None:
        """Newly-added CodeQL-sourced leaf context paths are auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(f'jobs:\n  build:\n    steps:\n      - run: echo "${{{{ {expr} }}}}"\n')

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    @pytest.mark.parametrize(
        "expr",
        [
            "github.event.comment",
            "github.event.issue",
            "github.event.pull_request",
            "github.event.review",
            "github.event.discussion",
            "github.event.head_commit",
            "github.event.merge_group",
            "github.event.workflow_run",
        ],
    )
    def test_whole_object_interpolation_fixed(self, tmp_path: Path, expr: str) -> None:
        """Whole-object interpolation (e.g. ${{ github.event.issue }}) is auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(f'jobs:\n  build:\n    steps:\n      - run: echo "${{{{ {expr} }}}}"\n')

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    @pytest.mark.parametrize(
        "expr",
        [
            "github.event.pull_request.number",
            "github.event.issue.number",
            "github.event.comment.id",
            "github.repository",
        ],
    )
    def test_trusted_leaf_of_whole_object_untouched(self, tmp_path: Path, expr: str) -> None:
        """Trusted leaves of a whole-object context (e.g. .number) stay untouched."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = f'jobs:\n  build:\n    steps:\n      - run: echo "${{{{ {expr} }}}}"\n'
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert wf.read_text() == original

    @pytest.mark.parametrize(
        "expr",
        [
            "github.event.commits[0].message",
            "github.event.commits[0].author.email",
            "github.event.pages[0].title",
            "github.event.pages[0].page_name",
            "github.event.workflow_run.pull_requests[0].head.ref",
            "github.event.workflow_run.referenced_workflows[0].path",
            "github.event.changes.title.from",
            "github.event.changes.body.from",
            "github.event.changes.head.ref.from",
        ],
    )
    def test_array_indexed_and_changes_leaf_context_fixed(self, tmp_path: Path, expr: str) -> None:
        """Array-indexed (commits[N].*, pages[N].*, ...) and changes.*.from leaf paths are auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(f'jobs:\n  build:\n    steps:\n      - run: echo "${{{{ {expr} }}}}"\n')

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    @pytest.mark.parametrize(
        "expr",
        [
            "github",
            "github.event",
            "github.event.commits",
            "github.event.pages",
            "github.event.workflow",
            "github.event.pull_request.head",
            "github.event.pull_request.head.repo",
            "github.event.head_commit.author",
            "github.event.head_commit.committer",
            "github.event.merge_group.committer",
            "github.event.workflow_run.head_branch",
            "github.event.workflow_run.head_commit",
            "github.event.workflow_run.head_commit.author",
            "github.event.workflow_run.head_commit.committer",
            "github.event.workflow_run.head_repository",
            "github.event.workflow_run.pull_requests",
        ],
    )
    def test_codeql_json_kind_whole_object_fixed(self, tmp_path: Path, expr: str) -> None:
        """Every CodeQL "json"-kind whole-object row from untrusted_event_properties.yml is auto-fixed."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(f'jobs:\n  build:\n    steps:\n      - run: echo "${{{{ {expr} }}}}"\n')

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed

    """Test bare $VAR/$env:VAR quoting runs unconditionally, not just for hoisted placeholders."""

    def test_preexisting_bare_var_quoted_with_no_untrusted_context(self, tmp_path: Path) -> None:
        """A pre-existing unquoted $VAR (from an existing env:) is quoted with zero GH-context findings."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: echo $TITLE\n        env:\n          TITLE: some-value\n",
        )

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings == []
        assert len(quoted_paths) == 1
        assert 'echo "$TITLE"' in wf.read_text()

    def test_preexisting_bare_env_var_pwsh_quoted(self, tmp_path: Path) -> None:
        """A pre-existing unquoted $env:VAR in a pwsh step is quoted with zero GH-context findings."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - shell: pwsh\n"
            "        run: Write-Output $env:TITLE\n"
            "        env:\n"
            "          TITLE: some-value\n",
        )

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings == []
        assert len(quoted_paths) == 1
        assert 'Write-Output "$env:TITLE"' in wf.read_text()

    def test_already_double_quoted_var_inside_command_substitution_not_requoted(self, tmp_path: Path) -> None:
        """A $VAR already double-quoted inside $(...) is not spuriously re-wrapped in extra quotes.

        Regression test: the outer `"..."` around the `$(...)` must not be mistaken for closing
        at the inner `"` that actually opens a quote *inside* the command substitution -- POSIX
        shell grammar restarts quote parsing from scratch inside `$(...)` regardless of the
        enclosing quote state.
        """
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - run: |\n"
            '          kubectl_cmds="$(echo -e "${kubectl_cmds}" | sed -e \'s/^[[:space:]]*//\')"\n'
            "        env:\n"
            "          kubectl_cmds: some-value\n",
        )

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert quoted_paths == []
        assert '""${kubectl_cmds}""' not in wf.read_text()

    def test_bare_var_inside_command_substitution_still_quoted(self, tmp_path: Path) -> None:
        """A bare (unquoted) $VAR inside $(...) is still quoted -- the fix isn't a blanket skip."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - run: |\n"
            "          result=$(echo $TITLE)\n"
            "        env:\n"
            "          TITLE: some-value\n",
        )

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert findings == []
        assert len(quoted_paths) == 1
        assert 'result=$(echo "$TITLE")' in wf.read_text()

    def test_bare_quoting_only_preserves_literal_block_style(self, tmp_path: Path) -> None:
        """Bare-quoting-only remediation (no untrusted expr) keeps `run: |` block-scalar style."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - run: |\n"
            '          echo "HOME is $HOME"\n'
            "          ./deploy.sh $UPSTREAM_AEM_INSTANCES\n"
            "        env:\n"
            "          UPSTREAM_AEM_INSTANCES: some-value\n",
        )

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)
        text = wf.read_text()

        # Assert
        assert modified
        assert findings == []
        assert len(quoted_paths) == 1
        assert "run: |" in text
        assert './deploy.sh "$UPSTREAM_AEM_INSTANCES"' in text

    def test_bare_quoting_only_preserves_folded_block_style(self, tmp_path: Path) -> None:
        """Bare-quoting-only remediation (no untrusted expr) keeps `run: >` folded block-scalar style."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - run: >\n"
            "          echo $TITLE\n"
            "        env:\n"
            "          TITLE: some-value\n",
        )

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)
        text = wf.read_text()

        # Assert
        assert modified
        assert findings == []
        assert len(quoted_paths) == 1
        assert "run: >" in text
        assert 'echo "$TITLE"' in text

    def test_no_bare_vars_no_quoting(self, tmp_path: Path) -> None:
        """A step with no untrusted context and no bare env-var reference is left untouched."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = "jobs:\n  build:\n    steps:\n      - run: echo hello\n"
        wf.write_text(original)

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert quoted_paths == []
        assert wf.read_text() == original

    def test_unconditional_quoting_idempotent(self, tmp_path: Path) -> None:
        """Running the fixer twice on an unconditionally-quoted step produces no further changes."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n      - run: echo $TITLE\n        env:\n          TITLE: some-value\n",
        )

        # Act
        fix_injection_file(wf, dry_run=False)
        modified_again, findings_again, quoted_again = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified_again
        assert findings_again == []
        assert quoted_again == []

    @pytest.mark.parametrize("special", ["$@", "$*", "$#", "$?", "$$", "$!", "$1", "$0"])
    def test_special_positional_vars_never_quoted(self, tmp_path: Path, special: str) -> None:
        """Bash special/positional parameters are never quoted (would change word-splitting semantics)."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = f"jobs:\n  build:\n    steps:\n      - run: echo {special}\n"
        wf.write_text(original)

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert quoted_paths == []
        assert wf.read_text() == original

    def test_command_substitution_never_quoted(self, tmp_path: Path) -> None:
        """$(...) command substitution is never treated as a bare var reference."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = "jobs:\n  build:\n    steps:\n      - run: echo $(date)\n"
        wf.write_text(original)

        # Act
        modified, findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert quoted_paths == []
        assert wf.read_text() == original

    def test_cmd_shell_never_quoted(self, tmp_path: Path) -> None:
        """cmd's %VAR% expands regardless of quoting; unconditional pass leaves cmd steps untouched."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = "jobs:\n  build:\n    steps:\n      - shell: cmd\n        run: echo %TITLE%\n"
        wf.write_text(original)

        # Act
        modified, _findings, quoted_paths = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert quoted_paths == []
        assert wf.read_text() == original


class TestPoisonableStepOutputs:
    """Test steps.<id>.outputs.* detection for known-poisonable producer steps."""

    def test_poisonable_action_output_hoisted(self, tmp_path: Path) -> None:
        """Output of a step using a poisonable action (ruby/setup-ruby) is hoisted."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - id: setup\n"
            "        uses: ruby/setup-ruby@v1\n"
            '      - run: echo "${{ steps.setup.outputs.something }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed
        assert findings[0].expr == "steps.setup.outputs.something"
        content = wf.read_text()
        assert "${{" not in content.split("env:")[0].split("uses: ruby/setup-ruby@v1")[1]

    def test_poisonable_command_output_hoisted(self, tmp_path: Path) -> None:
        """Output of a step whose run: script's first command is poisonable (mvn) is hoisted."""
        # Arrange
        wf = tmp_path / "wf.yml"
        wf.write_text(
            "jobs:\n  build:\n    steps:\n"
            "      - id: build\n"
            "        run: mvn -B verify\n"
            '      - run: echo "${{ steps.build.outputs.version }}"\n',
        )

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert modified
        assert len(findings) == 1
        assert findings[0].fixed
        assert findings[0].expr == "steps.build.outputs.version"

    def test_non_poisonable_step_output_left_untouched(self, tmp_path: Path) -> None:
        """Output of a step using a non-poisonable action (actions/checkout) is not flagged."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = (
            "jobs:\n  build:\n    steps:\n"
            "      - id: checkout\n"
            "        uses: actions/checkout@v4\n"
            '      - run: echo "${{ steps.checkout.outputs.ref }}"\n'
        )
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert wf.read_text() == original

    def test_unresolvable_step_id_left_untouched(self, tmp_path: Path) -> None:
        """A steps.<id>.outputs.* reference with no matching id: declared is left untouched."""
        # Arrange
        wf = tmp_path / "wf.yml"
        original = 'jobs:\n  build:\n    steps:\n      - run: echo "${{ steps.nonexistent.outputs.x }}"\n'
        wf.write_text(original)

        # Act
        modified, findings, _ = fix_injection_file(wf, dry_run=False)

        # Assert
        assert not modified
        assert findings == []
        assert wf.read_text() == original
