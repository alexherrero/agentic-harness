# Phase: review

**Status:** stub. Full spec coming.

**Purpose:** adversarial critique of recent work. "Assume the code contains bugs. Find them."

**Preconditions:**
- Deterministic gates (typecheck / lint / test / build) all pass
- There is a concrete artifact to review (commit, branch diff, or uncommitted change)

**Produces:** either a failing test, a specific `file.ts:line` defect report, or an explicit "no issues found" — logged for rejection-rate tracking.

**Does not produce:** prose critiques ("consider adding error handling"). Rejected.

**Invokes:** the `adversarial-reviewer` sub-agent in a fresh context. Reviewer sees the artifact + plan only, not the implementer's reasoning trace.
