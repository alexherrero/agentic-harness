# Pipeline: bugfix

**Status:** stub. Full spec coming.

**Purpose:** triage-first pipeline for bug reports. Replaces `/plan` + `/work` for bugs.

**Phases:**
1. **Report** — capture the bug report verbatim. Do not paraphrase.
2. **Analyze** — reproduce locally if possible; identify root cause (not just the first suspicious symptom). Write findings to `.harness/PLAN.md` as a single-task plan.
3. **Fix** — implement per `/work` discipline. Add a regression test that fails without the fix and passes with it.
4. **Verify** — deterministic gates + `/review`. Confirm the regression test exists.
