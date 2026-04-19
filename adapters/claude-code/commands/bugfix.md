---
description: Bug triage pipeline — Report → Analyze → Fix → Verify. Use instead of /plan+/work for bugs.
argument-hint: <bug report or issue link>
---

You are running the **bugfix** pipeline. Full spec: `harness/pipelines/bugfix.md` (stub).

**Bug report:** $ARGUMENTS

Four phases, run in order:

1. **Report** — capture the bug verbatim in `.harness/PLAN.md` under `## Report`. Do not paraphrase.
2. **Analyze** — reproduce locally if possible. Identify root cause, not just symptom. Write findings to `.harness/PLAN.md` under `## Analysis`.
3. **Fix** — implement the fix (one-task `/work` discipline). Add a regression test that fails without the fix and passes with it. This is mandatory — no regression test, no fix.
4. **Verify** — deterministic gates + adversarial `/review`. Confirm the regression test exists and guards the root cause.
