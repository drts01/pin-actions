# Part 1 corpus results

- Repositories scanned: **1996**
- With at least one workflow or action file: **1324**
- With at least one in-scope `uses:`: **1321**
- Fully `uses:`-pinned (denominator `N`): **168** — 12.7% of in-scope repositories,
  95% CI 11.0% to 14.6% _(expression-valued `uses:` excluded)_
- Unparsable YAML files encountered: **14**

| Residual mutable surface             | Count | Denominator | Share     | 95% CI         |
| ------------------------------------ | ----- | ----------- | --------- | -------------- |
| Any of the three (headline)          | 22    | 168         | **13.1%** | 8.8% to 19.0%  |
| Mutable container image (`X`)        | 12    | 168         | **7.1%**  | 4.1% to 12.1%  |
| Unpinned cross-repo `with.ref` (`Y`) | 5     | 168         | **3.0%**  | 1.3% to 6.8%   |
| Unpinned pre-commit rev in CI (`Z`)  | 5     | 8           | **62.5%** | 30.6% to 86.3% |

Excluded from the numerators as neither pinned nor statically mutable: 0 expression-valued `uses:`,
7 expression-valued `with.ref`, 7 expression-valued image refs.
Local `uses: ./...` actions (596) are out of scope.

## Sizing the full run

- `p_pin`, fully pinned share of scanned repositories: **8.4%**
- `p_precommit`, pre-commit-eligible share of `N`: **4.8%**
- Repositories to clone for a `Z` denominator of 1,000: **249,500**

Compare the last figure against the frame size in `frame.meta.json`.
When it exceeds the frame, `Z` cannot be measured to slide quality at this sampling frame;
widen the frame or demote `Z` to an anecdote.
