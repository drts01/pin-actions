# Project Name Alternatives

Working notes on renaming `pin-actions`.
Not part of the published documentation site.

## Why Now

Renaming is nearly free today and expensive in a month.

| Signal                   | State                                                       |
| ------------------------ | ----------------------------------------------------------- |
| `pyproject.toml` version | `0.1.0`                                                     |
| Git tags                 | none                                                        |
| PyPI                     | `pin-actions` is **not published** (`/pypi/.../json` → 404) |
| `CHANGELOG.md`           | `Unreleased` already contains breaking changes              |
| External consumers       | none known                                                  |

Checked 2026-10-17.
Decide before the first PyPI release; after that a rename costs a deprecation shim, a redirect, and user confusion.

## The Problem With the Current Name

The scope-limiting word is **`actions`**, not **`pin`**.

The tool no longer only pins GitHub Actions.
It pins reusable workflow refs, cross-repo checkout refs, job containers, service containers, `docker://` steps,
and pre-commit hook revisions, and it verifies commit provenance.
A reader who sees `pin-actions` will not guess that it touches `.pre-commit-config.yaml` or `services[*].image`.

Keep **`pin`**.
"Pin your actions to a commit SHA" is the exact phrasing used in GitHub's own hardening guide, OpenSSF material,
and every blog post on the subject.
It is the search term.
Trading it for something more clever costs discoverability that cannot be bought back.

## Naming Criteria

1. Contains or strongly implies "pin" — matches the term of art people search for.
2. Does not imply GitHub Actions exclusively.
3. Available on PyPI, and not already owned by a tool in this exact space.
4. Works as a CLI verb phrase: `<name> --provenance strict` should read as an instruction.
5. Unambiguous module name (`import <name>`), lowercase, no underscores in the distribution name.
6. Not confusable with an existing CI/CD security tool.

## Candidates

PyPI availability checked 2026-10-17 via `https://pypi.org/pypi/<name>/json`.
A 404 means the name is unregistered.

| Name          | PyPI      | Module        | Assessment                                                                                          |
| ------------- | --------- | ------------- | --------------------------------------------------------------------------------------------------- |
| **`pin-ci`**  | available | `pin_ci`      | **Recommended.** Keeps the search term, scopes to all of CI, reads well as a command, short.        |
| `pinref`      | available | `pinref`      | Strong alternate. "Any ref, not just actions" is literally the thesis. Slightly opaque at a glance. |
| `refpin`      | available | `refpin`      | Same idea, worse rhythm. Reads as a noun, not a command.                                            |
| `pin-refs`    | available | `pin_refs`    | Clear and honest, but the plural reads awkwardly as a CLI invocation.                               |
| `pin-actions` | available | `pin_actions` | Status quo. Only correct if the project recommits to GitHub Actions scope.                          |
| `rivet`       | **taken** | —             | Best metaphor (a pin is removable, a rivet is permanent) but squatted by an unrelated S3 library.   |
| `pinpoint`    | **taken** | —             | Taken by an unrelated geo toolkit. Also implies locating, not fastening.                            |
| `ratchet`     | **avoid** | —             | See below. Already the name of a direct competitor.                                                 |

### Recommendation

**`pin-ci`**, with `pinref` as the fallback if `pin-ci` reads as too GitHub-specific in context.

Rationale:

- `pin-ci --provenance strict` reads as an imperative sentence.
- "CI" correctly covers workflows, composite actions, containers, and pre-commit hooks without naming a vendor.
- It leaves room to support non-GitHub CI systems later without a second rename.
- Six characters, no ambiguity, no collision.

The main argument against: "CI" is broad enough that the name does not say *what* it pins.
That is what the tagline is for.

### Taglines to pair with the name

- "Pin every mutable reference in your CI to an immutable digest — and verify it belongs to the repo it claims to."
- "Immutable CI references, verified at write time."
- "Pin it, then prove it."

## Blocker: `ratchet` Is a Competitor, Not a Candidate

While checking name availability, `ratchet` surfaced as [`sethvargo/ratchet`](https://github.com/sethvargo/ratchet) —
"A tool for securing CI/CD workflows with version pinning," Go, Apache-2.0, ~969 stars, actively maintained
(last push 2026-07).

Two consequences:

1. **`ratchet` is unusable as a name.**
   It would collide head-on with an established tool in the identical niche.
2. **`ratchet` was a gap in `docs/explanation/comparison.md`.**
   It has since been verified against source and added to the comparison page.

What the source verification found:

- Covers six CI systems (GitHub Actions, GitLab CI, CircleCI, Cloud Build, Drone, Tekton).
- On GitHub Actions it matches `pin-actions` on action refs, reusable workflow refs, `docker://` steps,
  `container.image`, and `services[*].image`.
- Does **not** pin `with.ref` cross-repo checkouts or pre-commit hook revisions,
  and does **not** verify provenance.
- Its `-bake-delay` cooldown is broader than `--exclude-newer`:
  it covers `pin`, `update`, and `upgrade`, and applies to container images.
- Documented limitation: it normalizes all indentation to two spaces and ignores anchors and aliases.

That corrected two claims that were previously wrong in both the README and the comparison page.
`pin-actions` is **not** alone in pinning `services[*].image`, and it does **not** have the broadest cooldown.

## Rename Cost Checklist

If the rename proceeds, these are the touch points.

- [ ] `pyproject.toml`: `project.name`, `project.scripts` entry point, coverage/ruff/pyrefly path references
- [ ] `src/pin_actions/` → `src/pin_ci/`
- [ ] All intra-package imports and `src/pin_ci/__init__.py` exports
- [ ] `tests/`, `benchmarks/`, and `scripts/` imports, including `pin_actions.precommit`
- [ ] `tox.toml` environment and path references
- [ ] `zensical.toml`: `site_name`, `site_url`, nav paths, mkdocstrings module references
- [ ] `docs/**`: every `pin-actions` occurrence, including `reference/*.md` mkdocstrings identifiers
- [ ] `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`
- [ ] GitHub repository name, and therefore the Pages URL (`drts01.github.io/pin-actions` → new slug)
- [ ] `.pre-commit-config.yaml` self-reference, if any
- [ ] Fleet automation in `scripts/update_repos.py` — branch name `pin-actions`, PR title and body templates
- [ ] `CHANGELOG.md` entry under `Unreleased` → `### Breaking Changes`
- [ ] Reserve the old name on PyPI only if `pin-actions` is ever published first

Mechanical steps are low-risk; the GitHub Pages URL change is the only externally visible break,
and there are no external consumers yet.

## Open Questions

- Does the project intend to support GitLab CI, CircleCI, or Tekton?
  If yes, `pin-ci` is clearly right and `ratchet` becomes the primary competitor rather than `pinact`.
  If no, the GitHub-specific name is defensible and the rename is optional.
- Should the SCaLE 24x talk be submitted under the new name?
  The CFP closes 2026-11-01.
  Submitting under a name that then changes is worse than either option; decide the name first.
