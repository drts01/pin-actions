# Pin an Existing Repository End to End

Take a repository with ordinary, unpinned CI and leave it fully pinned — actions, reusable workflows,
cross-repo checkouts, container images, and service images —
with every new commit SHA provenance-checked before it is written.

**Time:** about 15 minutes.
**Prerequisites:** `git`, and `pinref` installed ([Getting Started](getting-started.md)).
A `GITHUB_TOKEN` is optional for this tutorial but strongly recommended;
without one you share the 60-requests-per-hour unauthenticated rate limit.

## 1. Create a Practice Repository

Work on a scratch repository first so you can read the diff without worrying about breaking a real pipeline.

```bash
mkdir -p /tmp/pin-tutorial/.github/workflows
cd /tmp/pin-tutorial
git init
```

Write `.github/workflows/ci.yml`:

```yaml
name: CI

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    container:
      image: python:3.13-slim
    services:
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@main
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4
        with:
          repository: octocat/Hello-World
          ref: master
      - uses: docker://alpine:3.19
      - run: pytest  # keep this comment
```

This file is deliberately pathological.
It contains every mutable-reference shape `pinref` handles, including one that is *already* pinned to a stale SHA.

Commit it so you have a clean baseline to diff against:

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add unpinned workflow"
```

## 2. See What Would Change

Run `pinref` from the repository root.
The defaults already target `.github/workflows`, so no `--paths` flag is needed:

```bash
pinref --diff
```

`--diff` writes nothing.
It prints a unified diff and exits `0` whether or not changes are pending, which makes it safe to run anywhere.

You should see something close to this:

```diff
-      image: python:3.13-slim
+      image: library/python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f # 3.13-slim
-        image: redis:7
+        image: library/redis@sha256:4fa24486b8bcca8eec45ee0eb166edc674795e53a2b53d1a9ef263eecebaac85 # 7
-      - uses: actions/checkout@v4
-      - uses: actions/setup-python@main
-      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4
+      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
+      - uses: actions/setup-python@ec52d0af729a7c50ced4261d17a07916f43f5b8e # main
+      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
         with:
           repository: octocat/Hello-World
-          ref: master
-      - uses: docker://alpine:3.19
+          ref: 7fd1a60b01f91b314f59955a4e4d4e80d8edf11d # master
+      - uses: docker://library/alpine@sha256:6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1 # 3.19
       - run: pytest  # keep this comment
```

Your SHAs and digests will differ from the ones printed here.
That is the point: these upstream refs move, and the output captures wherever they point today.

## 3. Read the Diff

Six distinct transformations happened in one pass.

| Source line                        | What it was                | What it became            | Why                                                        |
| ---------------------------------- | -------------------------- | ------------------------- | ---------------------------------------------------------- |
| `container.image`                  | `python:3.13-slim`         | `library/python@sha256:…` | Registry tags are mutable; the digest is content-addressed |
| `services.redis.image`             | `redis:7`                  | `library/redis@sha256:…`  | Service containers are pinned the same way                 |
| `uses: actions/checkout@v4`        | Mutable tag                | Commit SHA                | A tag can be force-pushed to point at new code             |
| `uses: actions/setup-python@main`  | Branch                     | Commit SHA                | A branch moves on every merge                              |
| `uses: actions/checkout@11bd7190…` | **Stale** SHA              | **Re-resolved** SHA       | `v4` moved since this was pinned; the pin had drifted      |
| `with.ref: master`                 | Cross-repo checkout branch | Commit SHA                | `actions/checkout` fetches arbitrary code from this ref    |

Three details are worth pausing on.

**Tag drift is corrected, not ignored.** The third step was already pinned.
`pinref` read the trailing `# v4` comment, asked GitHub where `v4` points *now*,
and rewrote the SHA because the tag had moved.
Pinning is not a one-time operation, and the trailing comment is what makes repinning possible.

**Image names are normalized.**
`python` becomes `library/python` because that is the registry's canonical name for an official image.
The digest is what matters; the name is just how you find it.

**Nothing else moved.**
`# keep this comment` survives, indentation is untouched, and `on: [push]` stays in flow style.
`pinref` edits the YAML syntax tree and compares the serialized result before writing,
so a file with nothing to change is never touched at all.

## 4. Apply the Changes

Drop `--diff` to write:

```bash
pinref
```

Then inspect the result with the tool you already trust:

```bash
git --no-pager diff
```

Run it a second time:

```bash
pinref
```

It reports no modifications.
The operation is idempotent — repeated runs converge rather than churn.

## 5. Turn On Provenance

Pinning to a commit SHA defeats tag hijacking.
It does **not** defeat an attacker who hands you a SHA that lives in a *fork* of the action.
GitHub serves fork commits from the upstream repository's API namespace,
so `actions/checkout@<attacker-sha>` resolves successfully and reads as legitimate in review.

`--provenance` closes that gap at the moment the SHA is written.
Start in `warn` mode on a repository you did not pin yourself:

```bash
git checkout .github/workflows/ci.yml
pinref --provenance warn
```

Every SHA in this tutorial verifies, so you will see no warnings.
Once a clean pass is confirmed, promote to `strict`:

```bash
git checkout .github/workflows/ci.yml
pinref --provenance strict
```

In `strict` mode an unverifiable SHA raises `UnverifiedProvenanceError` and the file is left untouched.
That is the mode to use in CI, where a failed job is the outcome you want.

## 6. Know the Blind Spot

Provenance is checked when `pinref` *writes* a SHA.
An already-pinned ref with **no trailing tag comment** is skipped entirely —
it is never re-resolved and never provenance-checked:

```yaml
- uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0
```

Run `pinref --provenance strict` against that line and you get "No files modified".
There is no recorded tag to re-resolve against, so the entry is left alone.

This is exactly the shape a hand-edited impostor SHA would take.
Treat the trailing comment as load-bearing: let `pinref` write your pins so the comment is always present,
and review any pin that arrives without one.

## 7. Commit

```bash
git add .github/workflows/ci.yml
git commit -m "ci: pin actions and images to immutable digests"
```

## 8. Keep It Pinned

A one-time pin decays.
New steps get added unpinned, and upstream tags keep moving.
Two mechanisms keep the repository converged:

- **Gate pull requests.**
    Run `pinref --diff --provenance strict` in CI so an unpinned ref cannot merge.
    See [Run in CI](../how-to/run-in-ci.md).
- **Repin on a schedule.**
    Run `pinref` periodically and open a pull request with the result,
    so tag drift surfaces as a reviewable change rather than silent staleness.

## 9. Clean Up

```bash
rm -rf /tmp/pin-tutorial
```

## Now Do It on Your Own Repository

The sequence is identical, with one change: start in `warn`, not `strict`.

```bash
cd /path/to/your/repo
pinref --diff                      # read the proposed changes
pinref --provenance warn           # apply, logging anything unverifiable
git --no-pager diff                     # review
```

Pre-existing pins in a real repository may be unverifiable for entirely benign reasons — a branch that was deleted,
or a commit that never had a pull request opened upstream.
Resolve those warnings, then move to `strict` permanently.

## Next Steps

- [Verify SHA Provenance](../how-to/verify-provenance.md) — what "verified" proves, what it costs, and its blind spot
- [Run in CI](../how-to/run-in-ci.md) — the gating workflow, already pinned
- [Update Pinned Tags](../how-to/update-pinned-tags.md) — moving `v4` forward to `v5` on purpose
- [Pin Pre-Commit Hooks](../how-to/pin-pre-commit-hooks.md) — the same treatment for `.pre-commit-config.yaml`
- [Threat Model](../explanation/threat-model.md) — the attacks this sequence does and does not stop
