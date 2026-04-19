# Phase: setup

**Status:** stub. Full spec coming.

**Purpose:** first-time project initialization. Run once per project (or after a major restructure).

**Produces:**
- `.harness/init.sh` — one-shot script to boot the dev environment
- `.harness/features.json` — initial feature list (may be empty or seeded from PRD)
- `.harness/progress.md` — empty log, ready for first `/work` session
- Updated `AGENTS.md` and `CLAUDE.md` if missing

**Does not produce:** a plan. That's what `/plan` is for. Setup is pure scaffolding.

**TODO:** write the full spec. Reference [phases/02-plan.md](02-plan.md) for the structural template.
