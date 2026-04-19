---
description: Pre-merge gate — verify clean state, all tasks done, CI green. Stop if not.
---

You are running the **release** phase. Full spec: `harness/phases/05-release.md` (stub).

Until the full spec lands, the minimum release gate is:

1. Confirm all tasks in `.harness/PLAN.md` are `[x]` and `Status: done`.
2. Confirm `/review` ran and findings were addressed.
3. Re-run deterministic gates on a clean working tree.
4. Update changelog / release notes if the project has them.
5. Confirm CI is green (`gh pr checks` if there's a PR).
6. Append to `.harness/progress.md`: `<date> /release — shipped`.

If any of the above fails, stop and report. Do not merge or tag.
