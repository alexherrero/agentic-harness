---
description: Implement exactly one task from .harness/PLAN.md. Stop after one.
---

You are running the **work** phase. Full spec: `harness/phases/03-work.md` (stub).

Until the full spec lands, the minimum discipline is:

1. Read `.harness/PLAN.md`. Identify the first unchecked task.
2. If no plan exists or no unchecked tasks remain — stop, tell the user to run `/plan` first.
3. Implement that single task. Write tests where the task's verification criteria call for them.
4. Run the project's deterministic gates locally (typecheck, lint, tests, build — whatever's defined in `.harness/init.sh` / package scripts).
5. Mark the task complete in `.harness/PLAN.md` (`[x]`).
6. Append to `.harness/progress.md`: `<date> /work — completed task "<title>"`.
7. Stop. Do not start the next task.
