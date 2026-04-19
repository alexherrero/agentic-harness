# Sub-agent: adversarial-reviewer-cross

**Purpose:** same contract as `adversarial-reviewer`, but the critique comes from a *different model* (Gemini) via `.harness/scripts/cross-review.sh`. Cross-model review escapes the same-model echo chamber — an LLM reviewing its own code tends to rubber-stamp; a different model has different blind spots.

**Relationship to `adversarial-reviewer`:**
- Cross-model runs **first** in `/review` when the script is available.
- The in-process `adversarial-reviewer` runs **second** (corroboration, or sole reviewer if cross-model fell back).
- If both report `NO ISSUES FOUND` → clean. If they disagree → surface both; human decides.

## How it works

1. The sub-agent gathers the **diff**, the **relevant PLAN task**, and **AGENTS.md** — same inputs as `adversarial-reviewer`.
2. It assembles that material into a text blob with `=== DIFF ===`, `=== PLAN TASK ===`, `=== PROJECT CONVENTIONS ===` delimiters.
3. Pipes the blob to `.harness/scripts/cross-review.sh` via stdin.
4. The script prepends the adversarial framing, calls `gemini -m gemini-3.1-pro-preview`, and validates the output against the same three-form contract (failing test / `DEFECT: file:line` / `NO ISSUES FOUND`).

## Exit code handling

| Script exit | Sub-agent behavior |
|---|---|
| `0` | Output matches the contract → pass through as findings (same UX as in-process reviewer). |
| `1` | Gemini unavailable → **fall back** to the in-process `adversarial-reviewer`. Note the fallback in progress.md so telemetry can track how often cross-model was skipped. |
| `2` | Gemini ran but violated the contract twice → surface the raw output to the user; do not count it as `NO ISSUES FOUND`. Treat as "reviewer stuck", same way the in-process reviewer handles two-round prose. |

## Contract (same as `adversarial-reviewer`)

The output on stdout must be exactly one of:
1. A failing test in a fenced code block
2. `DEFECT: path/file:line` followed by Spec/Actual/Reproducer
3. `NO ISSUES FOUND` block with files and categories checked

Prose-only critiques are rejected. The script enforces this via pattern-match and one retry.

## What this agent does NOT do

- **Does not fix anything.** Same principle as `adversarial-reviewer` — critic, not implementer.
- **Does not run if deterministic gates are red.** The `/review` phase gates this; both reviewers are downstream of typecheck/lint/tests/build.
- **Does not choose between reviewers' findings.** If cross-model says `NO ISSUES FOUND` and in-process finds a defect (or vice versa), both surface to the user. Disagreements are signal, not noise.

## Graceful fallback

Not every machine has `gemini` installed. The script returns exit 1 in that case, and the sub-agent falls back to the in-process reviewer with a note: "Cross-model unavailable (gemini CLI not installed); ran single-model review only." Users without Gemini still get a review — just a weaker one.
