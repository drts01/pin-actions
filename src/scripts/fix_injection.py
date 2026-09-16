#!/usr/bin/env -S uv run --with-editable . --script
"""Remediate GitHub Actions script-injection: hoist untrusted ${{ }} exprs out of run: into env:.

Detects attacker-controllable context expressions (issue/PR titles & bodies, comment
bodies, branch names, etc.) interpolated directly into ``run:`` shell steps -- the
classic GHSL script-injection pattern -- and mechanically rewrites them to the safe
``env:`` indirection form recommended by GitHub's own security hardening guide:

    - run: echo "Title was ${{ github.event.issue.title }}"
    # becomes:
    - run: echo "Title was $TITLE"
      env:
        TITLE: ${{ github.event.issue.title }}

Once a step is rewritten, *every* plain ``${{ }}`` expression in that step's ``run:``
text is hoisted to ``env:`` -- not just the untrusted ones. This matches CodeQL's
``actions/code-injection`` sink model: its taint-tracking sink is the whole ``Run``
script, and a residual ``${{ trusted.expr }}`` substitution left inline (e.g.
``${{ github.repository }}``) can still anchor a reported finding via a sibling
untrusted expression in the same step/script, even though that trusted expression is
never itself a source. Leaving one lone trusted expression in an otherwise-untouched
step is fine and is left alone (see ``test_trusted_expr_left_untouched``).

Static, network-free (no GitHub API calls). Only rewrites ``run:`` shell steps;
``actions/github-script``'s ``with.script`` is JavaScript, not shell, and is
reported only -- never auto-fixed.

The hoisted ``$VAR``/``$env:VAR`` reference is also requoted to match how the original
``${{ }}`` substitution behaved: bare/unquoted occurrences are wrapped in double quotes
(preventing word-splitting/globbing on the untrusted value), and occurrences originally
inside a single-quoted string -- which never interpolates ``$VAR`` -- are spliced out of
the literal so the value still expands (see ``_requote_placeholder``). This does not apply
to ``cmd``, whose ``%VAR%`` expands unconditionally regardless of quoting.
"""

import difflib
import re
import sys
from pathlib import Path
from typing import Any

import yamlrocks
from pin_actions.config import Settings
from pin_actions.errors import PinActionsError, YAMLParseError
from pydantic import Field

# GitHub Security Lab's documented list of attacker-controllable context paths.
# See: https://securitylab.github.com/resources/github-actions-untrusted-input/
UNTRUSTED_CONTEXTS = frozenset(
    {
        "github.event.issue.title",
        "github.event.issue.body",
        "github.event.pull_request.title",
        "github.event.pull_request.body",
        "github.event.pull_request.head.ref",
        "github.event.pull_request.head.label",
        "github.event.pull_request.head.repo.default_branch",
        "github.event.comment.body",
        "github.event.review.body",
        "github.event.review_comment.body",
        "github.event.discussion.title",
        "github.event.discussion.body",
        "github.event.pages",
        "github.event.commits",
        "github.event.head_commit.message",
        "github.event.head_commit.author.email",
        "github.event.head_commit.author.name",
        "github.event.workflow_run.head_branch",
        "github.event.workflow_run.display_title",
        "github.head_ref",
        # workflow_dispatch/workflow_call inputs: not anonymous (requires dispatch/call
        # access), but still an attacker-controllable string reaching a shell -- treated
        # the same as event-payload fields per GitHub's own hardening guidance. The bare
        # "inputs." prefix also covers composite action inputs (action.yml `inputs:`).
        "github.event.inputs",
        "inputs",
        # repository_dispatch: arbitrary external payload from whoever holds the dispatch token.
        "github.event.client_payload",
        "github.event.label.name",
        "github.event.milestone.title",
        "github.event.milestone.description",
        "github.event.check_run.output.title",
        "github.event.check_run.output.summary",
        "github.event.deployment_status.description",
        "github.event.release.name",
        "github.event.release.body",
    }
)


_EXPR_RE = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")
_DEFAULT_SHELL_VAR_SYNTAX = {
    "bash": "${}",
    "sh": "${}",
    "pwsh": "$env:{}",
    "powershell": "$env:{}",
    "cmd": "%{}%",
}
# Shells whose quoting rules we understand well enough to requote a hoisted $VAR
# reference so it behaves the same as the original ${{ }} substitution did:
# bash/sh and pwsh/powershell all treat single-quoted strings as fully literal (no
# variable expansion) and double-quoted strings as interpolating. cmd's %VAR%
# expansion happens regardless of quoting, so it has no analogous risk and is left
# out -- its placeholder is emitted bare, unchanged from prior behavior.
_SINGLE_QUOTE_SPLICE = {
    # Close the single-quoted string, splice in a double-quoted interpolation of the
    # var, then reopen the single-quoted string -- bash/sh string literals concatenate
    # by mere adjacency: 'a'"$VAR"'b'.
    "bash": "'\"{}\"'",
    "sh": "'\"{}\"'",
    # PowerShell has no adjacency-concatenation; '+' is required: 'a'+"$env:VAR"+'b'.
    "pwsh": "'+\"{}\"+'",
    "powershell": "'+\"{}\"+'",
}


class InjectionSettings(Settings):
    """CLI & environment configuration for fix-injection."""

    paths: list[Path] = Field(
        default_factory=lambda: [Path(".github/workflows"), Path("**/action.yml"), Path("**/action.yaml")],
    )


def _is_untrusted(expr: str) -> bool:
    """Check whether a bare ${{ }} expression body references a known-untrusted context.

    Conservative: function-call-wrapped expressions (``fromJSON(...)``, ``toJSON(...)``,
    ``format(...)``, etc.) are not pattern-matched here and are reported but not fixed,
    since the wrapped value's shape isn't guaranteed to be a plain string.
    """
    if "(" in expr:
        return False
    return any(expr == ctx or expr.startswith(f"{ctx}.") for ctx in UNTRUSTED_CONTEXTS)


def _line_quote_states(line: str) -> list[str]:
    """Compute the shell quote state ("none"/"single"/"double") in effect at each char of ``line``.

    A single left-to-right scan tracking ``'``/``"`` toggles and backslash-escaping inside
    double quotes (bash/sh/pwsh rules: single-quoted strings have zero escaping; unquoted and
    double-quoted contexts honor backslash-escaping of the next char). Limitation: state resets
    per line, so a quote opened via a backslash-continued line break isn't tracked -- such steps
    are rare and still get a syntactically-valid (if possibly misquoted) rewrite reported.
    """
    states: list[str] = []
    state = "none"
    escape_next = False
    for ch in line:
        states.append(state)
        if escape_next:
            escape_next = False
            continue
        if state == "single":
            if ch == "'":
                state = "none"
        elif state == "double":
            if ch == "\\":
                escape_next = True
            elif ch == '"':
                state = "none"
        elif ch == "'":
            state = "single"
        elif ch == '"':
            state = "double"
    return states


def _requote_placeholder(placeholder: str, state: str, shell: str) -> str:
    """Adjust a hoisted ``$VAR`` placeholder so it expands the same way the original ``${{ }}`` did.

    - ``"double"``: already inside an interpolating string -- leave the bare placeholder as-is.
    - ``"none"`` (bare/unquoted word): wrap in double quotes to prevent word-splitting/globbing
      on the env var's value (untrusted-input-controlled).
    - ``"single"``: single-quoted strings never interpolate, so the placeholder must be spliced
      out of the literal via :data:`_SINGLE_QUOTE_SPLICE` (close quote, interpolate, reopen quote).

    Only applied for shells in :data:`_SINGLE_QUOTE_SPLICE` (bash/sh/pwsh/powershell); ``cmd``'s
    ``%VAR%`` expands regardless of quoting, so its placeholder is always returned unchanged.
    """
    if shell not in _SINGLE_QUOTE_SPLICE:
        return placeholder
    if state == "single":
        return _SINGLE_QUOTE_SPLICE[shell].format(placeholder)
    if state == "none":
        return f'"{placeholder}"'
    return placeholder


def _hoist_expr_in_text(text: str, expr: str, placeholder: str, shell: str) -> str:
    """Replace every ``${{ expr }}`` occurrence of a specific expression in ``text``.

    ``placeholder`` is requoted per-occurrence based on the shell-quote context it sits in.

    Quote state is tracked per line (see :func:`_line_quote_states`); ``re.sub`` evaluates
    match positions against the original line, so per-match requoting here is unaffected by
    earlier replacements lengthening/shortening that same line within this call.
    """

    def _replace_line(line: str) -> str:
        states = _line_quote_states(line)

        def _sub(m: re.Match[str]) -> str:
            if m.group(1) != expr:
                return m.group(0)
            return _requote_placeholder(placeholder, states[m.start()], shell)

        return _EXPR_RE.sub(_sub, line)

    return "\n".join(_replace_line(line) for line in text.split("\n"))


def _var_name(expr: str, used: set[str]) -> str:
    """Derive a stable, unique shell-safe env var name from a context expression."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", expr).strip("_").upper() or "INPUT"
    name = base
    i = 1
    while name in used:
        i += 1
        name = f"{base}_{i}"
    used.add(name)
    return name


class InjectionFinding:
    """A single untrusted ${{ }} expression found in a run: step."""

    __slots__ = ("expr", "fixed", "item_path")

    def __init__(self, item_path: tuple[Any, ...], expr: str, *, fixed: bool) -> None:
        """Initialize with the step's item path, expression body, and fix status."""
        self.item_path = item_path
        self.expr = expr
        self.fixed = fixed


def _collect_run_steps(doc: Any) -> list[tuple[tuple[Any, ...], str]]:  # noqa: ANN401
    """Collect (item_path, value) for every ``run:`` scalar in the doc."""
    return [
        (item_path, value)
        for item_path, value in doc.walk()
        if item_path and item_path[-1] == "run" and isinstance(value, str)
    ]


def _step_shell(doc: Any, step_path: tuple[Any, ...]) -> str:  # noqa: ANN401
    """Resolve the shell for a step: its own ``shell:`` key, defaulting to ``bash``.

    Does not resolve ``jobs.<job>.defaults.run.shell``/top-level ``defaults`` --
    those steps are conservatively treated as unknown-shell and skipped.
    """
    try:
        return _get_path(doc, step_path)["shell"]
    except KeyError, TypeError, IndexError:
        return "bash"


def _set_path(doc: Any, item_path: tuple[Any, ...], value: str) -> None:  # noqa: ANN401
    """Assign ``value`` at ``item_path`` within ``doc``, writing through to the AST."""
    target = doc
    for key in item_path[:-1]:
        target = target[key]
    target[item_path[-1]] = value


def _get_path(doc: Any, item_path: tuple[Any, ...]) -> Any:  # noqa: ANN401
    """Walk ``item_path`` within ``doc``, returning the node at that path."""
    target = doc
    for key in item_path:
        target = target[key]
    return target


def _set_step_env(doc: Any, step_path: tuple[Any, ...], var: str, value: str) -> None:  # noqa: ANN401
    """Set ``step.env[var] = value``, creating the ``env:`` map on the step if absent."""
    step = _get_path(doc, step_path)
    try:
        env = step["env"]
    except KeyError, TypeError, IndexError:
        step["env"] = {var: value}
        return
    env[var] = value


def remediate_run_step(
    doc: Any,  # noqa: ANN401
    item_path: tuple[Any, ...],
    text: str,
    placeholders: dict[str, tuple[str, str]],
) -> list[InjectionFinding]:
    """Rewrite untrusted ${{ }} exprs in a single run: step's text to env: indirection.

    Args:
        doc: yamlrocks round-trip document to mutate.
        item_path: Path to the ``run:`` scalar (ends in ``"run"``).
        text: Current text of the ``run:`` step.
        placeholders: Mutated in place: maps a unique placeholder token to
            ``(rewritten_text, original_style)`` for multi-line (``literal``/``folded``)
            ``run:`` scalars, so the caller can splice a real block scalar back in after
            ``doc.to_yaml()`` -- see module docstring note on the ``yamlrocks`` limitation
            this works around.

    Returns:
        Findings for every untrusted expression encountered (fixed or report-only).
        Trusted expressions that were incidentally hoisted alongside an untrusted one
        in the same step (see module docstring) do not get their own finding.
    """
    exprs = _EXPR_RE.findall(text)
    unfixable = [e for e in exprs if "(" in e]
    untrusted = [e for e in exprs if e not in unfixable and _is_untrusted(e)]
    findings: list[InjectionFinding] = [InjectionFinding(item_path, e, fixed=False) for e in unfixable]
    if not untrusted:
        return findings

    # CodeQL's code-injection sink is the whole Run script, not the individual ${{ }}
    # substitution: a residual plain expression (even a trusted one, e.g.
    # github.repository) left inline once *any* untrusted expression is hoisted can
    # still anchor a reported finding via the sibling untrusted expression in the same
    # step. Hoist every remaining fixable expression alongside the untrusted ones so no
    # bare ${{ }} substitution survives in a step this function actually rewrites.
    to_hoist = [e for e in exprs if e not in unfixable]

    step_path = item_path[:-1]
    shell = _step_shell(doc, step_path)
    var_syntax = _DEFAULT_SHELL_VAR_SYNTAX.get(shell)

    if var_syntax is None:
        # Unknown/unsupported shell: report-only, don't attempt a rewrite we can't
        # guarantee is syntactically safe for that shell.
        findings.extend(InjectionFinding(item_path, e, fixed=False) for e in untrusted)
        return findings

    used_vars: set[str] = set()
    try:
        existing_env = dict(_get_path(doc, step_path)["env"])
    except KeyError, TypeError, IndexError:
        existing_env = {}
    used_vars.update(existing_env)

    new_text = text
    env_updates: dict[str, str] = {}
    seen: dict[str, str] = {}
    untrusted_set = set(untrusted)
    for expr in dict.fromkeys(to_hoist):  # dedupe, preserve first-seen order
        var = seen.get(expr) or _var_name(expr, used_vars)
        seen[expr] = var
        env_updates[var] = f"${{{{ {expr} }}}}"
        placeholder = var_syntax.format(var)
        new_text = _hoist_expr_in_text(new_text, expr, placeholder, shell)
        if expr in untrusted_set:
            findings.append(InjectionFinding(item_path, expr, fixed=True))

    original_style = doc.locate(item_path).style
    if original_style in ("literal", "folded"):
        # yamlrocks.YAMLRocksDocument.to_yaml() always re-emits a freshly-assigned
        # multi-line string as a double-quoted "a\nb\n" scalar after any mutation,
        # ignoring style hints (confirmed against yamlrocks 0.6.1; dumps() on a fresh
        # dict gets this right per https://yaml.rocks/guides/yaml-style/, but the
        # round-trip re-emit path does not). Work around it by writing a single-line
        # placeholder token now and splicing a real block scalar back into the
        # rendered YAML text afterwards -- see _splice_block_scalars.
        token = f"__PIN_ACTIONS_RUN_{len(placeholders)}__"
        placeholders[token] = (new_text, original_style)
        _set_path(doc, item_path, token)
    else:
        _set_path(doc, item_path, new_text)

    for var, value in env_updates.items():
        _set_step_env(doc, step_path, var, value)

    return findings


_PLACEHOLDER_LINE_RE = re.compile(r"^([ \t]*(?:-[ \t]+)?)([^\s:]+):[ \t]*(__PIN_ACTIONS_RUN_\d+__)[ \t]*$")


def _chomp_indicator(text: str) -> tuple[str, str]:
    """Pick the chomping indicator matching ``text``'s trailing newlines, and the content to emit.

    Returns ``(indicator, content)`` where ``content`` has no trailing newline (the emitted
    block-scalar lines), and ``indicator`` is ``"-"`` (strip, no trailing newline), ``""``
    (clip, exactly one trailing newline -- YAML's default), or ``"+"`` (keep, 2+ trailing
    newlines -- ``content`` then includes the extra blank line(s) explicitly).
    """
    if not text.endswith("\n"):
        return "-", text
    stripped = text.rstrip("\n")
    trailing = len(text) - len(stripped)
    if trailing <= 1:
        return "", stripped
    return "+", stripped + "\n" * (trailing - 1)


def _splice_block_scalars(rendered: bytes, placeholders: dict[str, tuple[str, str]]) -> bytes:
    """Replace placeholder-token lines with real literal/folded block scalars.

    Works around the ``yamlrocks`` round-trip re-emit limitation described in
    :func:`remediate_run_step`: a placeholder is emitted as a plain single-line scalar by
    ``doc.to_yaml()``, then swapped here for the hand-built multi-line block the original
    ``run:`` step used.
    """
    if not placeholders:
        return rendered

    lines = rendered.decode().split("\n")
    out: list[str] = []
    for line in lines:
        match = _PLACEHOLDER_LINE_RE.match(line)
        token = match.group(3) if match else None
        if token is None or token not in placeholders:
            out.append(line)
            continue

        prefix, key, _token = match.groups()
        text, style = placeholders[token]
        chomp, content = _chomp_indicator(text)
        indicator = {"literal": "|", "folded": ">"}[style] + chomp
        content_indent = " " * (len(prefix) + 2)
        out.append(f"{prefix}{key}: {indicator}")
        out.extend(f"{content_indent}{content_line}" if content_line else "" for content_line in content.split("\n"))

    return "\n".join(out).encode()


_SEQ_ITEM_LINE_RE = re.compile(r"^[ \t]*-([ \t]|$)")


def _strip_yamlrocks_blank_line_artifacts(rendered: bytes, original: bytes) -> bytes:
    """Work around a yamlrocks round-trip quirk that injects spurious blank lines.

    Confirmed against yamlrocks 0.6.1: any mutation to a round-trip ``YAMLRocksDocument``
    -- even one unrelated to a given block scalar -- causes ``doc.to_yaml()`` to insert an
    extra whitespace-only line (matching the next sequence item's indent) directly before
    a ``- `` sequence item that immediately follows a literal/folded (``|``/``>``) block
    scalar with no blank line separating them in the original source. Only lines matching
    that exact position (whitespace-only, immediately preceding a ``- `` line, and absent
    at that position in the original) are dropped -- intentional blank lines inside a kept
    (``|+``/``>+``) block scalar's own content are never touched, since those are followed
    by further block content, not a sequence marker.
    """
    original_lines = original.decode().split("\n")
    lines = rendered.decode().split("\n")
    cleaned: list[str] = []
    for i, line in enumerate(lines):
        is_artifact = (
            line.strip() == ""
            and line != ""
            and i + 1 < len(lines)
            and _SEQ_ITEM_LINE_RE.match(lines[i + 1])
            and line not in original_lines
        )
        if not is_artifact:
            cleaned.append(line)
    return "\n".join(cleaned).encode()


def fix_injection_file(
    path: Path,
    *,
    dry_run: bool = False,
    diff: bool = False,
) -> tuple[bool, list[InjectionFinding]]:
    """Detect and (unless dry_run) remediate script-injection in a single workflow/action file.

    Args:
        path: Path to a .yml/.yaml workflow or action file.
        dry_run: If True, don't write changes.
        diff: If True, print a unified diff of changes to stdout (implies dry_run).

    Returns:
        (modified, findings) -- whether the file was (or would be) modified, and every
        untrusted expression found (fixed or report-only).

    Raises:
        YAMLParseError: If the file cannot be parsed as YAML.
    """
    dry_run = dry_run or diff
    content = path.read_bytes()
    try:
        doc = yamlrocks.loads(content, option=yamlrocks.OPT_ROUND_TRIP)
    except Exception as exc:
        raise YAMLParseError(path, str(exc)) from exc

    if not isinstance(doc, yamlrocks.YAMLRocksDocument):
        raise YAMLParseError(path, "expected a round-trip YAMLRocksDocument")

    all_findings: list[InjectionFinding] = []
    placeholders: dict[str, tuple[str, str]] = {}
    for item_path, text in _collect_run_steps(doc):
        all_findings.extend(remediate_run_step(doc, item_path, text, placeholders))

    new_content = _strip_yamlrocks_blank_line_artifacts(_splice_block_scalars(doc.to_yaml(), placeholders), content)
    modified = new_content != content

    if diff and modified:
        sys.stdout.writelines(
            line + "\n"
            for line in difflib.unified_diff(
                content.decode().splitlines(),
                new_content.decode().splitlines(),
                fromfile=str(path),
                tofile=str(path),
                lineterm="",
            )
        )

    if modified and not dry_run:
        path.write_bytes(new_content)

    return modified, all_findings


def _resolve_files(paths: list[Path]) -> list[Path]:
    """Expand configured paths/globs into concrete workflow/action file paths."""
    cwd = Path()
    files: list[Path] = []
    for p in paths:
        if any(c in str(p) for c in ("*", "?", "[")):
            files.extend(cwd.glob(str(p)))
        elif not (cwd / p).exists():
            continue
        elif (cwd / p).is_file():
            files.append(cwd / p)
        else:
            files.extend(f for pattern in ("**/*.yml", "**/*.yaml") for f in (cwd / p).glob(pattern))
    return files


def _report_findings(findings: list[InjectionFinding], f: Path) -> int:
    """Print each finding (fixed to stdout, report-only to stderr); return report-only count."""
    report_only = 0
    for finding in findings:
        if finding.fixed:
            print(f"  fixed: {f} {finding.item_path}: {finding.expr}")
        else:
            print(f"  REVIEW (not auto-fixable): {f} {finding.item_path}: {finding.expr}", file=sys.stderr)
            report_only += 1
    return report_only


def main() -> None:
    """CLI entry point for fix-injection."""
    if "--version" in sys.argv:
        from pin_actions import __version__  # noqa: PLC0415 -- deferred to avoid import cost when unused

        print(f"fix-injection {__version__}")
        return

    try:
        settings = InjectionSettings(
            _cli_parse_args=True,
            _cli_kebab_case=True,
            _cli_implicit_flags=True,
            _cli_prog_name="fix-injection",
        )

        modified_files: list[Path] = []
        report_only_total = 0
        for f in _resolve_files(settings.paths):
            modified, findings = fix_injection_file(f, dry_run=settings.dry_run, diff=settings.diff)
            report_only_total += _report_findings(findings, f)
            if modified:
                modified_files.append(f)
    except PinActionsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if modified_files:
        print(f"Remediated {len(modified_files)} file(s):")
        for path in modified_files:
            print(f"  {path}")
    else:
        print("No files modified.")

    if report_only_total:
        print(f"{report_only_total} finding(s) require manual review (see stderr).", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
