# Remediate Code Injection

Rewrite untrusted `${{ }}` expressions in `run:` steps into GitHub's recommended `env:` indirection form,
using the bundled `fix_injection` console script.
Every scanned `run:` step also has its pre-existing bare `$VAR` references quoted.

The installed console script is named `fix_injection`; its `--help` banner displays the program name as `fix-injection`.
This page uses `fix_injection`, the name you type.

For why this rewrite is the correct fix, what the script treats as untrusted, and what it does not cover,
see [Script Injection in Workflow `run:` Steps](../explanation/code-injection.md).

## Preview the Changes

```bash
uv run fix_injection --diff
```

`--diff` prints a unified diff and implies `--dry-run`, so nothing is written.

By default the script scans `.github/workflows` — every `*.yml` and `*.yaml` file beneath it —
plus `**/action.yml` and `**/action.yaml`.
Pass `--paths` to scan different files, directories, or glob patterns.

## Apply the Changes

```bash
uv run fix_injection
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

The placeholder matches the step's shell: `bash`/`sh` get `$VAR`, `pwsh`/`powershell` get `$env:VAR`,
and `cmd` gets `%VAR%`.
Multi-line `run: |` (literal) and `run: >` (folded) block scalars keep their block style and real newlines.

## Findings That Require Manual Review

Some findings are printed to stderr, are not auto-fixed, and make the script exit with code `2`:

- **Function-wrapped expressions** (`fromJSON(...)`, `toJSON(...)`, `format(...)`, and similar) —
  the wrapped value is not guaranteed to be a plain string, so a mechanical `env:` hoist may not be safe.
- **Unrecognized `shell:` values** — no guaranteed-safe placeholder syntax exists for an unknown shell.

Rewrite these by hand, then re-run the script to confirm the file is clean.

## See Also

- [Explanation: Script Injection in Workflow `run:` Steps](../explanation/code-injection.md) —
    the sink, the untrusted-input taxonomy, and the scope boundaries
- [Explanation: Threat Model](../explanation/threat-model.md) —
    the supply-chain attack model `pin-actions` defends against
- Run `uv run fix_injection --help` for the full flag list
