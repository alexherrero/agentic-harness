# Phase: release

**Status:** stub. Full spec coming.

**Purpose:** pre-merge gate. Final check before the work goes live.

**Preconditions:**
- All tasks in the current `PLAN.md` are complete
- `/review` has been run and findings resolved
- Deterministic gates pass on a clean working tree

**Produces:**
- Changelog / release notes
- Version bump (where applicable)
- Clean commit history (squashed or rebased per project convention)
- Confirmation that CI is green
