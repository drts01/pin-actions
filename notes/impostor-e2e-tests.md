# Impostor-Commit End-to-End Tests (task 14)

Confirm or refute the source-code findings in
[`docs/explanation/mutable-references-across-platforms.md` §4](../docs/explanation/mutable-references-across-platforms.md)
before they appear on a slide as fact.

## Ground rules

- Use only accounts, groups, workspaces, and repositories you own.
- Make every payload a harmless marker: a file `marker.txt` containing `IMPOSTOR-<platform>-<date>`.
- Use no secrets, set the narrowest permissions the platform allows, and delete everything afterwards.
- Record each result in [Results](#results) with the date, the exact command, and the raw output or log line.
- Throughout, `C` is a commit that exists **only** in the fork,
  and `U` is the upstream repository the pin names.

## Common setup

1. Create upstream `U` with `main` containing `marker.txt` = `UPSTREAM` and, where needed, a CI template file.
2. Fork `U` to `F`.
3. On `F`, create branch `evil`, change `marker.txt` to the impostor marker, commit, push.
   Record the SHA as `C`.
4. Confirm `C` is absent from `U`'s branches and tags: `git ls-remote <U-url>` must not list `C`.

Every platform then runs the same two phases:

- **Phase A (shared storage):** run the checks with no pull or merge request open.
- **Phase B (PR/MR refs):** open a pull or merge request `F:evil → U:main`, do **not** merge it, and rerun the checks.

## GitHub (control, and live confirmation of task 13)

Phase A expectation: exposed.
Phase B expectation: exposed.
`pin-actions` should read unverified in both phases.

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/OWNER/U/commits/C                    # expect 200
git fetch --depth=1 https://github.com/OWNER/U.git C                # expect success
curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/OWNER/U/commits/C/pulls              # phase B: lists the open PR
```

```python
import asyncio
import os

from pin_actions.client import GitHubClient


async def main() -> None:
    async with GitHubClient(token=os.environ["GITHUB_TOKEN"]) as client:
        print(await client.verify_provenance("OWNER/U", "C"))  # expect "unverified" in both phases


asyncio.run(main())
```

Then the revert-and-squash variant: on `evil`, add a commit reverting the marker, squash-merge the PR,
and rerun the snippet on `C` (expect `unverified`) and on the squash commit (expect `verified`).

## GitLab (`gitlab.com` or a self-managed instance)

Source reading: path A not exposed; path B exposed for `include:project` and components;
`refs/keep-around/<sha>` may keep `C` resolvable after the MR ref is deleted.

Setup additions:

- In `U`, add `template.yml` (a job that runs `cat marker.txt`) and `templates/probe.yml` (a component).
- Create consumer project `K` in a different namespace.
- `U_ID` is `U`'s URL-encoded path, for example `group%2FU`.

Checks, run in both phases:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://gitlab.com/api/v4/projects/U_ID/repository/commits/C"   # A: expect 404; B: expect 200
git fetch --depth=1 https://gitlab.com/group/U.git C                # A: expect failure; B: expect success
git ls-remote https://gitlab.com/group/U.git 'refs/merge-requests/*' # B: expect .../head pointing at C
```

`include:project` via the CI lint API, so no pipeline has to run:

```bash
curl -sS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -H 'Content-Type: application/json' \
  -d '{"content": "include:\n  - project: group/U\n    ref: C\n    file: template.yml\n"}' \
  "https://gitlab.com/api/v4/projects/K_ID/ci/lint"
```

- Phase A expectation: an error containing ``reference `C` does not exist!``.
- Phase B expectation: `valid: true`, and the merged YAML contains the impostor job.

Component: repeat the lint call with `include:\n  - component: gitlab.com/group/U/probe@C\n`.
If it fails for a reason unrelated to the SHA, such as catalog publishing, record the message verbatim.

Keep-around: close the MR without merging.
After 15 days, confirm `refs/merge-requests/<iid>/head` is gone from `git ls-remote`,
then rerun the API and lint checks.
`valid: true` confirms the keep-around inference; ``does not exist!`` refutes it.

Finally, run one real pipeline in `K` with the phase B include, to confirm the job executes and prints the marker.

## Azure Pipelines (GitHub repository resource)

Source reading: the agent fetches `+<sha>` directly, so paths A and B are exposed at checkout.
Open questions: whether `ref:` accepts a raw SHA, and how compile-time templates resolve.

Setup: an Azure DevOps project with a GitHub service connection to the account owning `U`,
and a pipeline in any repository with `system.debug: true`.

```yaml
variables:
  system.debug: true
resources:
  repositories:
    - repository: up
      type: github
      endpoint: GITHUB_CONNECTION
      name: OWNER/U
      ref: C
steps:
  - checkout: up
  - script: cat marker.txt
```

| Run | Change                                                                                  | Expectation                                                                                        |
| --- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| 1   | As above, phase A                                                                       | Either a queue-time error rejecting `ref: C`, or a log line `fetch ... +C` and the impostor marker |
| 2   | As above, phase B                                                                       | Same as run 1                                                                                      |
| 3   | Add variable `VSTS.DisableFetchByCommit: true`                                          | Checkout fails to find `C` (control for the knob)                                                  |
| 4   | Replace the steps with `- template: probe.yml@up`, where `probe.yml` exists only in `C` | Records compile-time behavior, currently unverified                                                |

Search the log for `fetchByCommit : True` and `+C` and quote both.

## Bitbucket Cloud

Expectations: no PR refs, so path B is not exposed; path A undocumented; `import:` cannot pin a SHA.
Forks must stay in the parent workspace `W`.

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -u "USER:APP_PASSWORD" \
  https://api.bitbucket.org/2.0/repositories/W/U/commit/C            # path A answer
git fetch --depth=1 https://bitbucket.org/W/U.git C
git ls-remote https://bitbucket.org/W/U.git                         # phase B: look for any ref pointing at C
```

`import:` probe, in a consumer repository in `W`, with `U` exporting a pipeline:

```yaml
definitions:
  imports:
    shared: U:C
pipelines:
  default:
    import: probe@shared
```

Expect a validation error because `C` is not a branch or tag.
Quote it.

## Bitbucket Data Center

Expectation: `refs/pull-requests/<id>/from` exists, so path B is exposed to clients that fetch a SHA.
Run the `atlassian/bitbucket` container with an evaluation license, then:

```bash
git ls-remote http://localhost:7990/scm/PROJ/u.git 'refs/pull-requests/*'   # phase B: expect .../from at C
git fetch --depth=1 http://localhost:7990/scm/PROJ/u.git C
```

## Results

| Platform               | Check                   | Phase | Expected               | Observed | Date | Evidence |
| ---------------------- | ----------------------- | ----- | ---------------------- | -------- | ---- | -------- |
| GitHub                 | API / fetch             | A, B  | 200 / success          |          |      |          |
| GitHub                 | `verify_provenance`     | A, B  | `unverified`           |          |      |          |
| GitHub                 | squash after revert     | —     | `C` unverified         |          |      |          |
| GitLab                 | API / fetch             | A     | 404 / failure          |          |      |          |
| GitLab                 | API / fetch             | B     | 200 / success          |          |      |          |
| GitLab                 | `include:project` lint  | A     | `does not exist!`      |          |      |          |
| GitLab                 | `include:project` lint  | B     | `valid: true`          |          |      |          |
| GitLab                 | component lint          | B     | `valid: true`          |          |      |          |
| GitLab                 | keep-around after 15 d  | B     | `valid: true`          |          |      |          |
| Azure                  | checkout `ref: C`       | A, B  | `+C` fetch, marker     |          |      |          |
| Azure                  | knob control            | A     | failure                |          |      |          |
| Azure                  | template from `C`       | A, B  | unknown                |          |      |          |
| Bitbucket Cloud        | API / fetch             | A     | unknown                |          |      |          |
| Bitbucket Cloud        | refs after PR           | B     | no ref at `C`          |          |      |          |
| Bitbucket Cloud        | `import: U:C`           | —     | validation error       |          |      |          |
| Bitbucket Data Center  | PR refs / fetch         | B     | `from` ref, success    |          |      |          |

After filling this in, update the Confidence column in the cross-platform doc's §4 table
and remove the matching entries from its "Not yet verified" list.
