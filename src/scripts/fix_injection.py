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

In addition to context-path expressions, ``steps.<id>.outputs.*`` is also treated as
untrusted when ``<id>`` names a step that ran an action/command CodeQL's
``poisonable_steps.yml`` data model considers influenceable by attacker-controlled
repository content (e.g. ``mvn``, ``pytest``, ``ruby/setup-ruby``) -- see
:func:`_collect_poisonable_step_ids`. Outputs of steps outside that enumerated list are
not modeled and are left untouched, matching CodeQL's own scope.

Every bare/unquoted ``$VAR``/``$env:VAR`` reference in a step's ``run:`` text -- not
just ones this tool just hoisted -- is also (re)quoted to match how the original
``${{ }}`` substitution behaved: bare occurrences are wrapped in double quotes
(preventing word-splitting/globbing on the untrusted value), and occurrences originally
inside a single-quoted string -- which never interpolates ``$VAR`` -- are spliced out of
the literal so the value still expands (see ``_quote_bare_env_refs``). This does not apply
to ``cmd``, whose ``%VAR%`` expands unconditionally regardless of quoting.
"""

import difflib
import itertools
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yamlrocks
from pin_actions._yaml_artifacts import strip_blank_line_artifacts
from pin_actions.config import Settings
from pin_actions.errors import PinActionsError, YAMLParseError
from pydantic import Field

# GitHub Security Lab's documented list of attacker-controllable context paths, plus
# CodeQL's untrusted_event_properties data model (workflow_run/merge_group/head_commit
# committer fields, edited-event diffs, workflow path fields, array-indexed entries).
# See: https://securitylab.github.com/resources/github-actions-untrusted-input/
# See: https://github.com/github/codeql/blob/main/actions/ql/lib/ext/config/untrusted_event_properties.yml
#
# Array-indexed CodeQL entries (``commits[N].message``, ``pages[N].title``, ...) are
# expressed here with the ``[N]`` stripped (``commits.message``) since ``_is_untrusted``
# normalizes ``[<digits>]`` out of the checked expression before comparing -- see
# ``_INDEX_RE``.
_UNTRUSTED_LEAF_CONTEXTS = (
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.pull_request.title",
    "github.event.pull_request.body",
    "github.event.pull_request.head.ref",
    "github.event.pull_request.head.label",
    "github.event.pull_request.head.repo.default_branch",
    "github.event.pull_request.head.repo.homepage",
    "github.event.pull_request.head.repo.description",
    "github.event.comment.body",
    "github.event.review.body",
    "github.event.review_comment.body",
    "github.event.discussion.title",
    "github.event.discussion.body",
    "github.event.pages.page_name",
    "github.event.pages.title",
    "github.event.commits.message",
    "github.event.commits.author.email",
    "github.event.commits.author.name",
    "github.event.commits.committer.email",
    "github.event.commits.committer.name",
    "github.event.head_commit.message",
    "github.event.head_commit.author.email",
    "github.event.head_commit.author.name",
    "github.event.head_commit.committer.email",
    "github.event.head_commit.committer.name",
    "github.event.workflow_run.head_branch",
    "github.event.workflow_run.display_title",
    "github.event.workflow_run.head_commit.message",
    "github.event.workflow_run.head_commit.author.email",
    "github.event.workflow_run.head_commit.author.name",
    "github.event.workflow_run.head_commit.committer.email",
    "github.event.workflow_run.head_commit.committer.name",
    "github.event.workflow_run.head_repository.description",
    "github.event.workflow_run.pull_requests.head.ref",
    "github.event.workflow_run.path",
    "github.event.workflow_run.referenced_workflows.path",
    "github.event.merge_group.head_ref",
    "github.event.merge_group.committer.email",
    "github.event.merge_group.committer.name",
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
    # `changes.*` carries the *previous* value of an edited field (issue/PR edited
    # events) -- still attacker-controlled text, just historical rather than current.
    "github.event.changes.title.from",
    "github.event.changes.body.from",
    "github.event.changes.head.ref.from",
    "github.event.workflow.path",
)
# Whole-object contexts: exact-match only, never prefix-matched. Interpolating/
# toJSON-serializing a whole object (e.g. `${{ github.event.issue }}`) stringifies
# every leaf field, including untrusted ones (title/body/etc.), matching CodeQL's own
# "json"-kind data-model rows verbatim -- but the object also carries plainly-trusted
# leaves (`.number`, `.id`, ...) that must stay untouched when referenced directly as
# their own leaf path, so these can't prefix-match a dotted child expression the way a
# leaf context (e.g. `github.event.issue.title`) does.
_UNTRUSTED_WHOLE_OBJECT_CONTEXTS = (
    "github",
    "github.event",
    "github.event.comment",
    "github.event.commits",
    "github.event.issue",
    "github.event.pull_request",
    "github.event.pull_request.head",
    "github.event.pull_request.head.repo",
    "github.event.review",
    "github.event.discussion",
    "github.event.pages",
    "github.event.head_commit",
    "github.event.head_commit.author",
    "github.event.head_commit.committer",
    "github.event.merge_group",
    "github.event.merge_group.committer",
    "github.event.workflow",
    "github.event.workflow_run",
    "github.event.workflow_run.head_branch",
    "github.event.workflow_run.head_commit",
    "github.event.workflow_run.head_commit.author",
    "github.event.workflow_run.head_commit.committer",
    "github.event.workflow_run.head_repository",
    "github.event.workflow_run.pull_requests",
    "github.event.changes",
)
# Maps each untrusted context path to whether it is whole-object (see above).
UNTRUSTED_CONTEXTS: dict[str, bool] = dict.fromkeys(_UNTRUSTED_LEAF_CONTEXTS, False) | dict.fromkeys(
    _UNTRUSTED_WHOLE_OBJECT_CONTEXTS, True
)

# Strips GitHub Actions array-index syntax (e.g. the `[0]` in `github.event.commits[0].message`)
# so expressions can be compared against the index-free leaf paths in UNTRUSTED_CONTEXTS.
_INDEX_RE = re.compile(r"\[[0-9]+\]")

# CodeQL's poisonable_steps.yml data model: actions and shell commands whose output can be
# influenced by attacker-controlled repository content (e.g. a malicious pom.xml/package.json
# causing a build/lint/test tool to emit attacker-chosen text via a step output). A later
# step's ``steps.<id>.outputs.*`` reference is only treated as untrusted if the producing step
# (identified by its ``id:``) matches one of these -- see ``_collect_poisonable_step_ids``.
# See: https://github.com/github/codeql/blob/main/actions/ql/lib/ext/config/poisonable_steps.yml
_POISONABLE_ACTIONS = (
    "azure/powershell",
    "pre-commit/action",
    "oxsecurity/megalinter",
    "bridgecrewio/checkov-action",
    "ruby/setup-ruby",
    "actions/jekyll-build-pages",
    "qcastel/github-actions-maven/actions/maven",
    "sonarsource/sonarcloud-github-action",
)
_POISONABLE_COMMAND_RES = tuple(
    re.compile(regexp)
    for regexp in (
        r"ant",
        r"asv",
        r"awk\s+-f",
        r"bundle",
        r"bun",
        r"cargo",
        r"checkov",
        r"eslint",
        r"gcloud\s+builds submit",
        r"golangci-lint",
        r"gomplate",
        r"goreleaser",
        r"gradle",
        r"java\s+-jar",
        r"make",
        r"mdformat",
        r"mkdocs",
        r"msbuild",
        r"mvn",
        r"mypy",
        r"(p)?npm\s+[a-z]",
        r"pre-commit",
        r"prettier",
        r"phpstan",
        r"pip\s+install(.*)\s+-r",
        r"pip\s+install(.*)\s+--requirement",
        r"pip(x)?\s+install(.*)\s+\.",
        r"poetry",
        r"pylint",
        r"pytest",
        r"python[\d.]*\s+-m\s+pip\s+install\s+-r",
        r"python[\d.]*\s+-m\s+pip\s+install\s+--requirement",
        r"rake",
        r"rails\s+db:create",
        r"rails\s+assets:precompile",
        r"rubocop",
        r"sed\s+-f",
        r"sonar-scanner",
        r"stylelint",
        r"terraform",
        r"tflint",
        r"yarn",
        r"webpack",
    )
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


def _is_untrusted(expr: str, poisonable_ids: frozenset[str]) -> bool:
    """Check whether a bare ${{ }} expression body references a known-untrusted context.

    Conservative: function-call-wrapped expressions (``fromJSON(...)``, ``toJSON(...)``,
    ``format(...)``, etc.) are not pattern-matched here and are reported but not fixed,
    since the wrapped value's shape isn't guaranteed to be a plain string. Array-index
    syntax (``commits[0].message``) is normalized away before matching against the
    index-free paths in :data:`UNTRUSTED_CONTEXTS` -- see CodeQL's array-indexed
    ``untrusted_event_properties.yml`` rows (``commits[N].message``, ``pages[N].title``).

    ``steps.<id>.outputs.*`` is untrusted only if ``<id>`` is in ``poisonable_ids`` -- i.e. the
    producing step ran an action/command CodeQL's ``poisonable_steps.yml`` data model treats as
    influenceable by attacker-controlled repository content. See
    :func:`_collect_poisonable_step_ids`.
    """
    if "(" in expr:
        return False
    normalized = _INDEX_RE.sub("", expr)
    return any(
        normalized == ctx or (not whole_object and normalized.startswith(f"{ctx}."))
        for ctx, whole_object in UNTRUSTED_CONTEXTS.items()
    ) or any(normalized.startswith(f"steps.{sid}.outputs") for sid in poisonable_ids)


def _line_quote_states(line: str) -> list[str]:
    """Compute the shell quote state ("none"/"single"/"double") in effect at each char of ``line``.

    A left-to-right scan tracking ``'``/``"`` toggles and backslash-escaping inside double quotes
    (bash/sh/pwsh rules: single-quoted strings have zero escaping; unquoted and double-quoted
    contexts honor backslash-escaping of the next char). A stack of quote states is maintained so
    that ``$(...)`` command substitution -- which restarts quote parsing from scratch regardless
    of the enclosing quote state, per POSIX shell grammar -- is modeled: encountering ``$(`` while
    unquoted or double-quoted pushes a fresh ``"none"`` context, popped on the matching ``)``.
    Command substitution inside single quotes is *not* special (single quotes suppress all
    expansion), so a literal ``$(`` there is left as plain characters. Limitation: state resets
    per line, so a quote opened via a backslash-continued line break isn't tracked -- such steps
    are rare and still get a syntactically-valid (if possibly misquoted) rewrite reported.
    """
    states: list[str] = []
    stack: list[tuple[str, bool]] = [("none", False)]  # (state, is_subshell_frame)
    escape_next = False
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        state, _in_subshell = stack[-1]
        states.append(state)
        consumed = 1
        if escape_next:
            escape_next = False
        elif state == "single":
            if ch == "'":
                stack.pop()
        elif state == "double":
            if ch == "\\":
                escape_next = True
            elif ch == '"':
                stack.pop()
            elif ch == "$" and line[i + 1 : i + 2] == "(":
                stack.append(("none", True))
                states.append(state)
                consumed = 2
        elif ch == "'":
            stack.append(("single", False))
        elif ch == '"':
            stack.append(("double", False))
        elif ch == "$" and line[i + 1 : i + 2] == "(":
            stack.append(("none", True))
            states.append(state)
            consumed = 2
        elif ch == ")" and len(stack) > 1 and stack[-1][1]:
            stack.pop()
        i += consumed
    return states


def _hoist_expr_in_text(text: str, expr: str, placeholder: str) -> str:
    """Replace every ``${{ expr }}`` occurrence of a specific expression in ``text`` with a bare placeholder.

    Quoting to match the original ``${{ }}`` substitution's expansion behavior is handled
    separately by :func:`_quote_bare_env_refs`, which runs unconditionally over the whole
    step text (including pre-existing var references, not just newly-hoisted ones).
    """
    return _EXPR_RE.sub(lambda m: placeholder if m.group(1) == expr else m.group(0), text)


_VAR_REF_RE = {
    "bash": re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"),
    "sh": re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"),
    "pwsh": re.compile(r"\$env:([A-Za-z_][A-Za-z0-9_]*)"),
    "powershell": re.compile(r"\$env:([A-Za-z_][A-Za-z0-9_]*)"),
}


def _quote_bare_env_refs(text: str, shell: str) -> str:
    """Quote every bare (unquoted) shell env-var reference in ``text`` to prevent word-splitting/globbing.

    Runs unconditionally over a step's full ``run:`` text -- not just placeholders this tool
    just hoisted -- so pre-existing unquoted ``$VAR``/``$env:VAR`` references are also hardened
    (classic ShellCheck SC2086). Single-quoted occurrences (which never interpolate) are spliced
    out of the literal via :data:`_SINGLE_QUOTE_SPLICE`; double-quoted occurrences are left as-is.
    ``$(...)``/``$((...))`` substitution and bash special/positional parameters (``$@``, ``$1``,
    ...) never match :data:`_VAR_REF_RE` (it requires an identifier start) and so are untouched.
    Only applied for shells in :data:`_SINGLE_QUOTE_SPLICE`; ``cmd``'s ``%VAR%`` expands
    regardless of quoting.
    """
    var_re = _VAR_REF_RE.get(shell)
    if var_re is None:
        return text

    def _replace_line(line: str) -> str:
        states = _line_quote_states(line)

        def _sub(m: re.Match[str]) -> str:
            state = states[m.start()]
            if state == "single":
                return _SINGLE_QUOTE_SPLICE[shell].format(m.group(0))
            if state == "none":
                return f'"{m.group(0)}"'
            return m.group(0)

        return var_re.sub(_sub, line)

    return "\n".join(_replace_line(line) for line in text.split("\n"))


def _var_name(expr: str, used: set[str]) -> str:
    """Derive a stable, unique shell-safe env var name from a context expression."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", expr).strip("_").upper() or "INPUT"
    name = next(n for i in itertools.count() if (n := base if i == 0 else f"{base}_{i + 1}") not in used)
    used.add(name)
    return name


@dataclass(slots=True, frozen=True)
class InjectionFinding:
    """A single untrusted ${{ }} expression found in a run: step."""

    item_path: tuple[Any, ...]
    expr: str
    fixed: bool


def _collect_run_steps(doc: Any) -> list[tuple[tuple[Any, ...], str]]:  # noqa: ANN401
    """Collect (item_path, value) for every ``run:`` scalar in the doc."""
    return [
        (item_path, value)
        for item_path, value in doc.walk()
        if item_path and item_path[-1] == "run" and isinstance(value, str)
    ]


def _first_command(script: str) -> str:
    """Return the first non-blank, non-comment line of a ``run:`` script (mirrors CodeQL's ``getACommand()``)."""
    return next((line.strip() for line in script.split("\n") if line.strip() and not line.strip().startswith("#")), "")


def _collect_poisonable_step_ids(doc: Any) -> frozenset[str]:  # noqa: ANN401
    """Collect the ``id:`` of every step whose action/command CodeQL treats as poisonable.

    A step is poisonable if its ``uses:`` callee (ref/version stripped) is in
    :data:`_POISONABLE_ACTIONS`, or its ``run:`` script's first command matches any of
    :data:`_POISONABLE_COMMAND_RES` -- mirroring CodeQL's ``DangerousActionUsesStep``/
    ``PoisonableCommandStep`` classes. Steps without an ``id:`` can't be referenced via
    ``steps.<id>.outputs.*`` and are skipped.
    """
    ids: set[str] = set()
    for item_path, value in doc.walk():
        if not item_path or item_path[-1] != "id" or not isinstance(value, str):
            continue
        step = _get_path(doc, item_path[:-1])
        uses = _try_get(step, "uses")
        run = _try_get(step, "run")
        if (isinstance(uses, str) and uses.split("@", 1)[0] in _POISONABLE_ACTIONS) or (
            isinstance(run, str) and any(cmd_re.match(_first_command(run)) for cmd_re in _POISONABLE_COMMAND_RES)
        ):
            ids.add(value)
    return frozenset(ids)


def _step_shell(doc: Any, step_path: tuple[Any, ...]) -> str:  # noqa: ANN401
    """Resolve the shell for a step: its own ``shell:`` key, defaulting to ``bash``.

    Does not resolve ``jobs.<job>.defaults.run.shell``/top-level ``defaults`` --
    those steps are conservatively treated as unknown-shell and skipped.
    """
    return _try_get(_get_path(doc, step_path), "shell", "bash")


def _try_get(mapping: Any, key: str, default: Any = None) -> Any:  # noqa: ANN401
    """Return ``mapping[key]``, or ``default`` if the key/index is absent or ``mapping`` doesn't support it."""
    try:
        return mapping[key]
    except KeyError, TypeError, IndexError:
        return default


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
    if (env := _try_get(step, "env")) is None:
        step["env"] = {var: value}
    else:
        env[var] = value


def remediate_run_step(
    doc: Any,  # noqa: ANN401
    item_path: tuple[Any, ...],
    text: str,
    placeholders: dict[str, tuple[str, str]],
    poisonable_ids: frozenset[str],
) -> tuple[list[InjectionFinding], bool]:
    """Rewrite untrusted ${{ }} exprs in a single run: step's text to env: indirection.

    Also unconditionally quotes bare env-var references in the step (see
    :func:`_quote_bare_env_refs`) -- independent of whether any untrusted expression was
    found, so pre-existing unquoted ``$VAR`` references are hardened too.

    Args:
        doc: yamlrocks round-trip document to mutate.
        item_path: Path to the ``run:`` scalar (ends in ``"run"``).
        text: Current text of the ``run:`` step.
        placeholders: Mutated in place: maps a unique placeholder token to
            ``(rewritten_text, original_style)`` for multi-line (``literal``/``folded``)
            ``run:`` scalars, so the caller can splice a real block scalar back in after
            ``doc.to_yaml()`` -- see module docstring note on the ``yamlrocks`` limitation
            this works around.
        poisonable_ids: Step ``id:`` values whose ``steps.<id>.outputs.*`` references are
            untrusted -- see :func:`_collect_poisonable_step_ids`.

    Returns:
        ``(findings, quoted)`` -- findings for every untrusted expression encountered
        (fixed or report-only; trusted expressions incidentally hoisted alongside an
        untrusted one do not get their own finding), and whether bare env-var quoting
        changed the step independent of any untrusted finding.
    """
    exprs = _EXPR_RE.findall(text)
    unfixable = [e for e in exprs if "(" in e]
    untrusted = [e for e in exprs if e not in unfixable and _is_untrusted(e, poisonable_ids)]
    findings: list[InjectionFinding] = [InjectionFinding(item_path, e, fixed=False) for e in unfixable]

    step_path = item_path[:-1]
    shell = _step_shell(doc, step_path)

    if not untrusted:
        quoted_text = _quote_bare_env_refs(text, shell)
        quoted = quoted_text != text
        if quoted:
            original_style = doc.locate(item_path).style
            if original_style in ("literal", "folded"):
                # Same yamlrocks round-trip limitation as the untrusted-hoist branch below:
                # a freshly-assigned multi-line string is always re-emitted as an escaped
                # double-quoted scalar, so route through the placeholder/splice workaround
                # even when the only change is bare env-var quoting.
                token = f"__PIN_ACTIONS_RUN_{len(placeholders)}__"
                placeholders[token] = (quoted_text, original_style)
                _set_path(doc, item_path, token)
            else:
                _set_path(doc, item_path, quoted_text)
        return findings, quoted

    var_syntax = _DEFAULT_SHELL_VAR_SYNTAX.get(shell)
    if var_syntax is None:
        # Unknown/unsupported shell: report-only, don't attempt a rewrite we can't
        # guarantee is syntactically safe for that shell.
        findings.extend(InjectionFinding(item_path, e, fixed=False) for e in untrusted)
        return findings, False

    # CodeQL's code-injection sink is the whole Run script, not the individual ${{ }}
    # substitution: a residual plain expression (even a trusted one, e.g.
    # github.repository) left inline once *any* untrusted expression is hoisted can
    # still anchor a reported finding via the sibling untrusted expression in the same
    # step. Hoist every remaining fixable expression alongside the untrusted ones so no
    # bare ${{ }} substitution survives in a step this function actually rewrites.
    to_hoist = [e for e in exprs if e not in unfixable]

    used_vars: set[str] = set(_try_get(_get_path(doc, step_path), "env", {}))

    new_text = text
    env_updates: dict[str, str] = {}
    seen: dict[str, str] = {}
    untrusted_set = set(untrusted)
    for expr in dict.fromkeys(to_hoist):  # dedupe, preserve first-seen order
        var = seen.get(expr) or _var_name(expr, used_vars)
        seen[expr] = var
        env_updates[var] = f"${{{{ {expr} }}}}"
        placeholder = var_syntax.format(var)
        new_text = _hoist_expr_in_text(new_text, expr, placeholder)
        if expr in untrusted_set:
            findings.append(InjectionFinding(item_path, expr, fixed=True))

    new_text = _quote_bare_env_refs(new_text, shell)

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

    return findings, False


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


def fix_injection_file(
    path: Path,
    *,
    dry_run: bool = False,
    diff: bool = False,
) -> tuple[bool, list[InjectionFinding], list[tuple[Any, ...]]]:
    """Detect and (unless dry_run) remediate script-injection in a single workflow/action file.

    Args:
        path: Path to a .yml/.yaml workflow or action file.
        dry_run: If True, don't write changes.
        diff: If True, print a unified diff of changes to stdout (implies dry_run).

    Returns:
        (modified, findings, quoted_paths) -- whether the file was (or would be) modified,
        every untrusted expression found (fixed or report-only), and the ``run:`` item paths
        where bare env-var references were quoted independent of any untrusted finding.

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
    quoted_paths: list[tuple[Any, ...]] = []
    placeholders: dict[str, tuple[str, str]] = {}
    poisonable_ids = _collect_poisonable_step_ids(doc)
    for item_path, text in _collect_run_steps(doc):
        findings, quoted = remediate_run_step(doc, item_path, text, placeholders, poisonable_ids)
        all_findings.extend(findings)
        if quoted:
            quoted_paths.append(item_path)

    new_content = strip_blank_line_artifacts(_splice_block_scalars(doc.to_yaml(), placeholders), content)
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

    return modified, all_findings, quoted_paths


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


def _report_findings(findings: list[InjectionFinding], quoted_paths: list[tuple[Any, ...]], f: Path) -> int:
    """Print each finding/quoting change (fixed/quoted to stdout, report-only to stderr).

    Returns:
        Count of report-only (not auto-fixable) findings.
    """
    report_only = 0
    for finding in findings:
        if finding.fixed:
            print(f"  fixed: {f} {finding.item_path}: {finding.expr}")
        else:
            print(f"  REVIEW (not auto-fixable): {f} {finding.item_path}: {finding.expr}", file=sys.stderr)
            report_only += 1
    for item_path in quoted_paths:
        print(f"  quoted: {f} {item_path}: bare env-var reference(s) quoted")
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
            modified, findings, quoted_paths = fix_injection_file(f, dry_run=settings.dry_run, diff=settings.diff)
            report_only_total += _report_findings(findings, quoted_paths, f)
            if modified:
                modified_files.append(f)

    except (PinActionsError, ValueError) as exc:
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
