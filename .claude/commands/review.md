---
description: Adversarial review — assume the code has bugs, find them. Executable artifact required.
---

You are running the **review** phase. Full spec: `harness/phases/04-review.md` + `harness/agents/adversarial-reviewer.md`.

1. Run deterministic gates first (typecheck, lint, tests, build). If any fail, stop and report — review comes after they're green.
2. Dispatch the `adversarial-reviewer` sub-agent (or follow its spec inline in a fresh context) with the framing: **"the code under review likely contains bugs — find them."**
3. The reviewer sees the diff + the relevant `.harness/PLAN.md` task + project `AGENTS.md`. It does NOT see the implementer's reasoning trace.
4. Required output: a failing test, a specific `file:line` defect, or an explicit "NO ISSUES FOUND" with categories checked.
5. Prose-only critiques are rejected — re-run if the reviewer returns one.
6. Append to `.harness/progress.md`: `<date> /review — <outcome>`.
