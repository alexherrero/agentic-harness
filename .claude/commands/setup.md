---
description: First-time project scaffold — init.sh, features.json, progress.md. Run once per project.
---

You are running the **setup** phase of the agentic-harness workflow. Full spec: `harness/phases/01-setup.md` (stub — use your judgment following the principles in `harness/principles.md`).

This phase is currently stubbed. Until the full spec lands, the minimum setup is:

1. Confirm `.harness/` exists in the project (create if not).
2. Copy the templates from the harness repo into `.harness/` if they don't already exist: `PLAN.md`, `features.json`, `progress.md`, `init.sh`.
3. Edit `.harness/init.sh` so it actually boots this project's dev environment.
4. Ensure `AGENTS.md` and `CLAUDE.md` reference the harness.
5. Append to `.harness/progress.md`: `<date> /setup — initialized harness for this project`.

Do not plan or implement anything. Setup is pure scaffolding.
