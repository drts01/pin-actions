# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo~=0.25",
# ]
# ///
# ruff: noqa: ANN001, ANN202, PLC0415, PLR1711
"""Slides for the SCaLE 24x talk on mutable references in GitHub Actions workflows.

Run from the repository root:

    uvx marimo edit --sandbox notes/scale-24x-slides.py

Every number on a data slide is computed from ``notes/corpus/corpus.csv`` through
``corpus_scanner.report.summarize``, the same aggregation that produced ``report-full.md``.
Speaker notes and slide types live in ``notes/layouts/scale-24x-slides.slides.json``.
The file-level ``noqa`` covers marimo's generated cell signatures, cell-local imports, and bare returns.
"""

import marimo

__generated_with = "0.25.2"
app = marimo.App(
    width="medium",
    app_title="You Pinned Your Actions. You're Still Not Pinned.",
)


@app.cell(hide_code=True)
def _():
    import marimo as mo
    from corpus_scanner.report import summarize, wilson

    return mo, summarize, wilson


@app.cell(hide_code=True)
def _(mo, summarize):
    s = summarize(mo.notebook_dir() / "corpus" / "corpus.csv", exclude_dynamic=True)
    return (s,)


@app.cell(hide_code=True)
def _(mo, wilson):
    def pct(hits: int, total: int) -> str:
        return f"{100 * hits / total:.1f}%"

    def ci(hits: int, total: int) -> str:
        low, high = wilson(hits, total)
        return f"95% CI {100 * low:.1f}% to {100 * high:.1f}%"

    def bar(label: str, hits: int, total: int) -> mo.Html:
        width = 100 * hits / total
        return mo.Html(
            f"""
            <div style="margin: 1rem 0">
              <div style="display: flex; justify-content: space-between; font-size: 1.15rem">
                <span>{label}</span>
                <span><b>{pct(hits, total)}</b> &nbsp; {hits:,} of {total:,} &nbsp; ({ci(hits, total)})</span>
              </div>
              <div style="background: var(--slate-4, #e2e8f0); border-radius: 4px; height: 1.2rem">
                <div style="width: {width:.1f}%; background: var(--blue-9, #2563eb);
                            height: 100%; border-radius: 4px"></div>
              </div>
            </div>
            """
        )

    return bar, ci, pct


@app.cell(hide_code=True)
def _(mo):
    mo.hstack(
        [
            mo.md(
                """
                `.github/workflows/ci.yml`

                ```yaml
                jobs:
                  test:
                    runs-on: ubuntu-latest
                    container:
                      image: python:3.14-slim
                    services:
                      redis:
                        image: redis:7
                    steps:
                      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
                        with:
                          persist-credentials: false
                      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
                        with:
                          repository: example-org/shared-config
                          ref: main
                          path: shared-config
                          persist-credentials: false
                      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
                      - run: uv run pre-commit run --all-files
                ```
                """
            ),
            mo.md(
                """
                `.pre-commit-config.yaml`

                ```yaml
                repos:
                  - repo: https://github.com/astral-sh/ruff-pre-commit
                    rev: v0.17.0
                    hooks:
                      - id: ruff-check
                ```

                ## Every `uses:` is pinned to a commit SHA.

                ## How many mutable references are left?
                """
            ),
        ],
        widths=[3, 2],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.hstack(
        [
            mo.md(
                """
                ```yaml
                jobs:
                  test:
                    runs-on: ubuntu-latest
                    container:
                      image: python:3.14-slim          # (1) mutable tag
                    services:
                      redis:
                        image: redis:7                 # (2) mutable tag
                    steps:
                      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
                        with:
                          persist-credentials: false
                      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
                        with:
                          repository: example-org/shared-config
                          ref: main                    # (3) mutable branch
                          path: shared-config
                          persist-credentials: false
                      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
                      - run: uv run pre-commit run --all-files
                ```
                """
            ),
            mo.md(
                """
                ```yaml
                repos:
                  - repo: https://github.com/astral-sh/ruff-pre-commit
                    rev: v0.17.0                       # (4) mutable tag
                    hooks:
                      - id: ruff-check
                ```

                # Four.

                Each one can change what runs in this job
                without a single line of this repository changing.
                """
            ),
        ],
        widths=[3, 2],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # Now look at the SHAs you *did* pin.

        ```text
        actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        ```

        ## How do you know that commit came from `actions/checkout`?
        """
    ).center()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # You Pinned Your Actions.
        # You're Still Not Pinned.

        ### Measuring the mutable references SHA pinning leaves behind

        Carlos Meza &nbsp; | &nbsp; SCaLE 24x &nbsp; | &nbsp; Pasadena, April 2027
        """
    ).center()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("# Tags are pointers. Pointers move."),
            mo.mermaid(
                """
                graph LR
                    T["uses: some/action@v4"] --> A["commit you reviewed"]
                    T -. "force-push by maintainer or attacker" .-> B["commit nobody reviewed"]
                    S["uses: some/action@a1b2c3...(40 hex)"] --> A
                """
            ),
            mo.md(
                """
                A commit SHA names content.
                Changing the content changes the SHA.
                That is why "pin to a SHA" became the standard advice.
                """
            ),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md("# This is not hypothetical"),
            mo.callout(
                mo.md(
                    """
                    **Pending fact-check (task 9).**
                    Add one incident in which a moved tag shipped malicious code to consumers:
                    timeline, CVE identifier, and whether SHA-pinned consumers were affected,
                    each cited to a primary source.
                    Do not present incident details from memory.
                    """
                ),
                kind="warn",
            ),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(ci, mo, pct, s):
    _unpinned = s.in_scope - s.pinned
    mo.vstack(
        [
            mo.md("# The advice is universal. Compliance is not."),
            mo.stat(
                value=pct(_unpinned, s.in_scope),
                label="of repositories using actions from other repositories do not pin all of them to a commit SHA",
                caption=f"{_unpinned:,} of {s.in_scope:,} ({ci(_unpinned, s.in_scope)})",
                bordered=True,
            ),
            mo.md(
                f"""
                Sample: {s.scanned:,} active, non-archived, non-fork public repositories with at least 100 stars.
                Denominator: repositories with at least one non-local, non-expression `uses:`.
                """
            ),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # The platform answer: workflow dependency lockfiles

    - `.github/workflows/actions.lock`, generated by `gh actions-lock`
    - Records the requested `ref`, the resolved `commit`, and the source repository's numeric identity
    - GitHub verifies that identity at run time and requires the commit to exist on a branch of that repository
    - Covers transitive action dependencies, which SHA pinning in your own file cannot
    - GitHub's position: for repositories that adopt one, it supersedes SHA pinning

    **Status: public preview.** Adopt it when you can. Most of this room cannot yet.

    [docs.github.com: Workflow dependency lockfiles](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Part 1: The surface the advice misses

    "Pin your actions" and the lockfile both address **`uses:`**.

    A workflow runs code from more places than that:

    - job containers
    - service containers
    - `docker://` steps
    - cross-repository checkouts
    - pre-commit hooks
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Six mutable references, and what controlling one gets an attacker

    | Reference | Example | What an attacker who controls it gets |
    | --- | --- | --- |
    | Action ref | `uses: org/action@v4` | Arbitrary code in the job, with the job's token |
    | Reusable workflow ref | `uses: org/repo/.github/workflows/x.yml@main` | Arbitrary jobs, plus inherited secrets |
    | Cross-repo checkout ref | `with: {repository: org/x, ref: main}` | Arbitrary source on disk, often built or run |
    | `docker://` step image | `uses: docker://alpine:3` | Arbitrary code in the job |
    | Job container image | `container: python:3.14-slim` | The environment every step runs inside |
    | Service container image | `services.redis.image: redis:7` | A trusted service on the job's network |

    Pre-commit `rev:` values that CI runs are mutable too.
    So are `runs-on:` runner images, which no pinning tool covers.
    """)
    return


@app.cell(hide_code=True)
def _(mo, s):
    mo.md(f"""
    # How I measured it

    - **Frame:** public repositories with at least 100 stars, pushed since 2026-04-01, not forks, not archived
    - **Sample:** seeded 50,000-repository draw; {s.scanned:,} still existed
    - **Snapshot:** default branch only, pinned by each repository's HEAD SHA
    - **In scope:** {s.in_scope:,} repositories with at least one non-local, non-expression `uses:`
    - **`N`:** {s.pinned:,} repositories where *every* in-scope `uses:` is a 40-character commit SHA
    - **Mutable:** an image without a `sha256:` digest; a `with.ref` or `rev:` that is not a commit SHA
    - **Excluded:** local actions, and expression-valued refs such as `${{{{ github.sha }}}}`
    - **Intervals:** 95% Wilson score intervals, with every denominator shown

    Scanner, sampling inputs, seed, and raw counts are published with these slides.
    """)
    return


@app.cell(hide_code=True)
def _(ci, mo, pct, s):
    mo.vstack(
        [
            mo.md(f"# Of {s.pinned:,} repositories that pinned every `uses:` to a commit SHA"),
            mo.stat(
                value=pct(s.any_gap, s.pinned),
                label="still run at least one mutable container image, checkout ref, or pre-commit revision",
                caption=f"{s.any_gap:,} of {s.pinned:,} ({ci(s.any_gap, s.pinned)})",
                bordered=True,
            ),
            mo.md("## About one in seven."),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(bar, mo, s):
    mo.vstack(
        [
            mo.md("# Where the residual surface is"),
            bar("Any of the three", s.any_gap, s.pinned),
            bar("Mutable container image", s.image_gap, s.pinned),
            bar("Cross-repository <code>with.ref</code> not pinned to a SHA", s.withref_gap, s.pinned),
            mo.md("---"),
            bar(
                "Pre-commit revision not pinned to a SHA (repositories running pre-commit in CI)",
                s.precommit_gap,
                s.precommit_eligible,
            ),
            mo.md(
                f"""
                The pre-commit figure has its own, smaller denominator: {s.precommit_eligible:,} repositories.
                Treat it as supporting evidence, not a headline.
                """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, pct, s):
    _none = s.pinned - s.any_gap
    mo.md(
        f"""
        # The deflating reading, said out loud

        {pct(_none, s.pinned)} of fully pinned repositories show none of these three.

        That does **not** mean they are clean. The scanner does not count:

        - Docker container action definitions (`runs.image` in an `action.yml`)
        - `runs-on:` runner images
        - history: only the default-branch snapshot
        - repositories below 100 stars, where pinning discipline plausibly differs

        The point is not that the gap is enormous.
        It is that the gap exists, nobody had measured it, and no standard guide tells you to look.
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # The measurement found a gap in my own tool

    GitHub documents two forms of job container:

    ```yaml
    container:
      image: node:20     # the mapping form: detected

    container: node:20   # the string shorthand: missed
    ```

    Fixed before the scan ran.
    The pinning surface is larger than anyone's mental model of it, including mine.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Who covers what

    | Mutable reference | Lockfile (preview) | ratchet | pinact | Updatecli | pin-github-action | zizmor | pinref |
    | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
    | Action ref | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
    | Reusable workflow ref | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠️ | ✅ |
    | Cross-repo checkout ref | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
    | `docker://` step image | ❌ | ✅ | ❌ | ✅ | ❌ | ⚠️ | ✅ |
    | Job container image | ❌ | ✅ | ❌ | ✅ | ❌ | ⚠️ | ✅ |
    | Service container image | ❌ | ✅ | ❌ | ❌ | ❌ | ⚠️ | ✅ |
    | Pre-commit revision | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ | ✅ |
    | Provenance of the SHA | ✅ run time | ❌ | ❌ | ❌ | ❌ | ⚠️ after commit | ✅ write time |

    ✅ pins or verifies &nbsp; ⚠️ reports only &nbsp; ❌ not covered

    Disclosure: I maintain pinref.
    `ratchet` also covers five other CI systems; pinref covers GitHub Actions only.
    Based on documentation and source review, October 2026.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # Part 2: A SHA is not a promise

        A commit SHA fixes **content**.

        It does not tell you **where the commit came from**.
        """
    ).center()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # GitHub says so, in its own documentation

    > Commits pushed to any repository in a network can be accessible from other repositories in that network,
    > including the upstream repository.
    >
    > [About forks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks)

    > When selecting a SHA, you should verify it is from the action's repository and not a repository fork.
    >
    > [Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)

    One sentence. It tells you to verify, and not how.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Demo: a commit that exists only in my fork

                1. Fork the upstream repository and push a commit that prints a marker to the job log
                2. Ask the **upstream** repository's API for that SHA: it answers 200
                3. Pin the upstream name to the fork-only SHA in a workflow or `.pre-commit-config.yaml`
                4. Run it: the marker appears
                5. Run the pinning tools against the same reference and compare what each one does

                Throwaway organization, `permissions: {}`, no secrets.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **Pending reproduction (tasks 6, 7, 12).**
                    Prefer the pre-commit variant if it reproduces; fall back to an action.
                    Show only tool behavior observed in testing. Play the recording if the network fails.
                    """
                ),
                kind="warn",
            ),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Would you catch this in review?

                ```diff
                 steps:
                -  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
                +  - uses: actions/checkout@<fork-only-sha> # v7.0.1
                     with:
                       persist-credentials: false
                ```

                Right repository name. Right version comment. Forty hex characters.
                """
            ),
            mo.callout(
                mo.md("Replace `<fork-only-sha>` with the SHA from the reproduced demo (task 6)."),
                kind="warn",
            ),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Who checks where the SHA came from

    | Control | When | How |
    | --- | --- | --- |
    | GitHub lockfile (preview) | Run time | Repository ID, and the commit must be on a branch |
    | `zizmor` `impostor-commit` | After the SHA is committed | Static audit; detects, does not prevent |
    | `pinref --provenance strict` | Before the SHA is written | Refuses SHAs not reachable on the named repository |
    | Other pinning tools reviewed | | Resolve and write the SHA without an origin check |

    The last row comes from source review; confirm it empirically before claiming it (task 7).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # What "verified" means here

    A SHA counts as coming from the named repository when it is:

    - the head of a branch,
    - a tagged commit, or
    - the head or merge commit of a **merged** pull request.

    **Open pull requests do not count**: anyone can open one, and opening it copies the commit into the
    upstream repository.

    This is best-effort reachability through GitHub's API, **not** cryptographic attestation.
    A maintainer who merges a malicious pull request defeats it by design.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # Part 3: Controls, and what they cost

        Pinning is a policy you maintain, not a one-time fix.
        """
    ).center()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Pin images to digests, and keep the original tag readable

    ```yaml
    services:
      redis:
        image: redis:7@sha256:<digest>   # the tag stays for humans; the digest decides what runs
    ```

    ```yaml
    - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
    ```

    The trailing version comment is what lets reviewers, Dependabot, and Renovate keep working.
    Do not strip it.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # The cost: a pinned digest stops receiving patches

    | Policy | Risk you accept |
    | --- | --- |
    | Mutable tag | Whatever the publisher, or an attacker, pushes next |
    | Digest, never updated | Every CVE fixed upstream after you pinned |
    | Digest + automated updates | Review load for update pull requests |
    | Digest + updates + release cooldown | Patch latency equal to the cooldown window |

    Pair digest pins with Renovate or Dependabot digest updates, and choose the cooldown deliberately.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # What remediation changes, and where it fails

                - Files and references changed per repository
                - References that cannot be resolved, and why
                - Files that cannot be parsed
                - Review cost of the first pinning pull request
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **Pending public-corpus dry run (task 17).**
                    Fill this slide from reproducible results only.
                    Do not present internal fleet data without clearance.
                    """
                ),
                kind="warn",
            ),
        ],
        gap=2,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # A detector and a fixer are different jobs

    | Layer | Examples | What it does |
    | --- | --- | --- |
    | Platform | Workflow dependency lockfile | Pins and verifies action dependencies at run time |
    | Fixer | ratchet, pinact, Updatecli, pinref | Rewrites references to SHAs and digests |
    | Updater | Dependabot, Renovate | Keeps pins current through pull requests |
    | Detector | zizmor, actionlint | Finds what slipped through, plus other vulnerability classes |

    Use more than one. They overlap less than their names suggest.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Checklist

    1. Pin every `uses:` to a commit SHA with a version comment, or adopt a lockfile once you can.
    2. Verify that any new SHA is reachable on the repository it claims to come from.
    3. Search for `image:` and `docker://`, not just `uses:`; pin images to `sha256:` digests.
    4. Search for `ref:` under `with:` on cross-repository checkouts.
    5. Pin `.pre-commit-config.yaml` revisions to commit SHAs.
    6. Automate updates, and set a release cooldown on purpose.
    7. Run a detector and a fixer; they are different jobs.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Resources

    - Corpus scanner, sampling inputs, seed, and raw counts: *repository URL to be published with the talk*
    - [GitHub: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
    - [GitHub: About forks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks)
    - [GitHub: Workflow dependency lockfiles](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles)
    - [zizmor](https://github.com/zizmorcore/zizmor) &nbsp; [ratchet](https://github.com/sethvargo/ratchet)
      &nbsp; [pinact](https://github.com/suzuki-shunsuke/pinact) &nbsp; [Updatecli](https://github.com/updatecli/updatecli)
    - [pinref](https://github.com/drts01/pinref) (disclosure: I maintain it)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        # Questions

        You pinned your actions.
        Now go check everything else.
        """
    ).center()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Backup: Is this only GitHub?

    - **Image tags are mutable on every registry** under the OCI Distribution Spec.
      Docker Hub and Amazon ECR tag immutability is a publisher setting; consumers cannot observe or require it.
    - **CircleCI** registry orbs are immutable by construction, yet its own orb documentation
      defines an executor as `cimg/ruby:<< parameters.tag >>` with a default tag of `'2.7'`.
    - **GitLab** `include:project` and CI components resolve a pinned SHA without a branch or tag check.
      A merge request copies the contributor's commit into the target project.
      From source review, not yet tested.
    """)
    return


@app.cell(hide_code=True)
def _(ci, mo, s):
    mo.md(f"""
    # Backup: The pre-commit denominator

    - {s.precommit_gap:,} of {s.precommit_eligible:,} repositories that run pre-commit in CI have a revision
      that is not a commit SHA ({ci(s.precommit_gap, s.precommit_eligible)}).
    - Those {s.precommit_eligible:,} repositories are {100 * s.precommit_eligible / s.pinned:.1f}% of `N`.
    - A 1,000-repository denominator would need a frame wider than the one sampled.

    Reported as supporting evidence with its own denominator, not as the headline.
    """)
    return


if __name__ == "__main__":
    app.run()
