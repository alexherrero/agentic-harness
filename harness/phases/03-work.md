# Phase: work

**Status:** stub. Full spec coming.

**Purpose:** execute exactly one task from `.harness/PLAN.md`.

**Preconditions:**
- `.harness/PLAN.md` exists and has at least one unchecked task
- Working tree is clean (or has only intentional in-progress work)

**Produces:**
- Code changes implementing the selected task
- Tests for the task (where applicable)
- Updated `.harness/PLAN.md` — task marked complete
- Appended `.harness/progress.md` entry

**Non-negotiable:** stop after one task. Do not start the next task "while you're in there."
