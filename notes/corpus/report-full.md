# Part 1 corpus results

- Repositories scanned: **49984**
- With at least one workflow or action file: **32950**
- With at least one in-scope `uses:`: **32863**
- Fully `uses:`-pinned (denominator `N`): **4008** — 12.2% of in-scope repositories,
  95% CI 11.8% to 12.6% _(expression-valued `uses:` excluded)_
- Unparsable YAML files encountered: **35**

| Residual mutable surface             | Count | Denominator | Share     | 95% CI         |
| ------------------------------------ | ----- | ----------- | --------- | -------------- |
| Any of the three (headline)          | 592   | 4008        | **14.8%** | 13.7% to 15.9% |
| Mutable container image (`X`)        | 358   | 4008        | **8.9%**  | 8.1% to 9.9%   |
| Unpinned cross-repo `with.ref` (`Y`) | 113   | 4008        | **2.8%**  | 2.4% to 3.4%   |
| Unpinned pre-commit rev in CI (`Z`)  | 163   | 204         | **79.9%** | 73.9% to 84.8% |

Excluded from the in-scope denominator: 1 repository with expression-valued `uses:`.
Excluded from the residual numerators as neither pinned nor statically mutable: 532 expression-valued `with.ref`,
342 expression-valued image refs.
Local `uses: ./...` and `uses: $/...` actions (14645) are out of scope.

## Sizing the full run

- `p_pin`, fully pinned share of scanned repositories: **8.0%**
- `p_precommit`, pre-commit-eligible share of `N`: **5.1%**
- Repositories to clone for a `Z` denominator of 1,000: **245,020**

Compare the last figure against the frame size in `frame.meta.json`.
When it exceeds the frame, `Z` cannot be measured to slide quality at this sampling frame;
widen the frame or demote `Z` to an anecdote.
