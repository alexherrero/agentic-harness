# Phase: plan

Turn a brief into `.harness/PLAN.md` — a structured, executable plan with per-task verification criteria. No code is written in this phase.

## Purpose

A plan exists so that:
1. The implementer (a later `/work` session) has a shared contract to work against — not a verbal understanding that evaporates with context.
2. Scope is fixed *before* you're deep in code, where fixing it costs more.
3. Verification criteria are pre-negotiated, which is the single biggest lever on review quality (see [principles.md §5](../principles.md)).
4. The work is broken into pieces small enough that one `/work` session can finish each one.

## Preconditions

- `.harness/` directory exists (if not, run `/setup` first).
- The user has provided a brief — either as free text, a ticket link, or a reference to an existing document. If the brief is ambiguous, interview before planning (see §Interview below).

## Inputs

- **The brief** — what the user wants built or changed.
- **`.harness/PLAN.md`** if it exists — is there a plan in flight? If so, are we continuing it or starting a fresh one?
- **The codebase** — enough context to decompose the work realistically. Use the `explorer` sub-agent for read-only fan-out if the brief spans unfamiliar code.

## Process

### 1. Triage existing state

- Read `.harness/PLAN.md` if it exists.
- If it's in flight (`Status: in-progress`) and the new brief looks related: ask the user "continue the current plan, or replace it?" Do not silently overwrite.
- If it's complete (`Status: done`) or absent: proceed to a fresh plan.
- Read `.harness/progress.md` — what's the last thing that happened in this project? Useful context.

### 2. Interview, if the brief is ambiguous

The single most valuable thing this phase does. Adapted from [Trail of Bits' "interview first, implement second"](https://github.com/trailofbits/claude-code-config).

Before writing the plan, confirm:
- **Scope boundary.** What's explicitly out of scope? Name at least one thing.
- **Success criterion.** How will we know this is done? If the user can't answer, the plan is premature.
- **Non-obvious constraints.** Performance budgets, compatibility requirements, deadlines, regulated behavior.
- **Risk surface.** What part of the system is this most likely to break? What's load-bearing near the change?

Keep the interview to ≤5 questions, batch them, and default to *not asking* if the answer is derivable from the brief or codebase. Interview fatigue is a real failure mode.

### 3. Decompose into tasks

Each task should be:
- **Small enough** that one `/work` session can finish it (rough heuristic: a task a human would commit as one PR).
- **Independently verifiable** — it has its own pass/fail criteria.
- **Ordered** — dependencies explicit. Later tasks may assume earlier tasks are done.
- **Concretely scoped** — "refactor the auth layer" is not a task. "Extract `verifyToken` into `auth/verify.ts` and add unit tests for expired/malformed/valid inputs" is.

**Rule of thumb:** if you can't describe a task's verification in one sentence, split it further.

### 4. Write `.harness/PLAN.md`

Use the template at [`templates/PLAN.md`](../../templates/PLAN.md). Structure:

```markdown
# Plan: <short title>

**Status:** planning | in-progress | done
**Created:** <YYYY-MM-DD>
**Brief:** <1-3 sentence restatement of what we're building>

## Goal

<What success looks like in 2-4 sentences. User-facing, not implementation-flavored.>

## Constraints

- <Non-obvious constraint 1>
- <Non-obvious constraint 2>

## Out of scope

- <Explicit non-goal 1>
- <Explicit non-goal 2>

## Tasks

### 1. <Task title>
- **What:** <1-2 sentences>
- **Verification:** <how we'll know this is done — executable if possible>
- **Status:** [ ] | [x]

### 2. <Task title>
- **What:** ...
- **Verification:** ...
- **Status:** [ ]

## Risks / open questions

- <Risk 1 — what could go wrong, what we'll do if it does>
- <Open question 1 — something we may need to decide mid-work>

Keep this section short. Most plans have 0–2 real risks; padding with generic ones ("what if the API changes?") is noise. If there are no real risks, write "None identified" — don't invent.

## Verification strategy

<Which deterministic gates apply. Any project-specific extras, e.g. "must manually test on iOS Safari.">
```

### 4b. External-review handoff (optional, alternative to inline iteration — v2.3.1+)

After writing the draft `.harness/PLAN.md`, the operator has an alternative to iterating with the agent inline: hand off to an external editor (typically Antigravity IDE with Gemini) for review + revision. Useful when the plan is long or the operator prefers Antigravity's native inline-comment UI for thinking through changes.

**When to offer this option**: after `.harness/PLAN.md` is written + before declaring "done" with the planning phase, ask:

> "Plan is drafted. Iterate inline (review tasks together here), or hand off for external review in Antigravity?"

**On "hand off for external review"**:

1. **Write pre-handoff snapshot** at `.harness/PLAN.pre-handoff-<YYYYMMDDhhmmss>.md` — full copy of the drafted PLAN.md as it stands when the operator picks "Hand off". Used on resume to diff against the externally-revised version.

2. **Generate transfer-context file** at `.harness/transfer/plan-<YYYYMMDDhhmmss>.md`. Uses the template at `agent-toolkit/skills/design/templates/transfer-context.md` (the toolkit-side template — shared across `/design` skill + harness `/plan` for handoff consistency). Fill placeholders:

   - `DOC_TITLE` = PLAN.md's title
   - `DOC_TYPE` = `plan`
   - `OPERATOR_INTENT_PARAGRAPH` = lift from the brief + Goal sections
   - `RECENT_DECISIONS_BULLETS` = the plan's `## Locked design calls` section (if present) + the most recent `.harness/progress.md` entry's noted decisions
   - `INLINED-CONVENTIONS-dev-flow` = static expansion (paragraph-long Status:[x] narratives / ✅⬜ charts / link blocks / wake-on-CI / NEVER append Co-Authored-By trailer / etc.)
   - `INLINED-GUARDRAILS-FOR-plan` = harness PLAN.md shape per `templates/PLAN.md`; Status lifecycle `draft → in-progress → done` (don't transition; only `/work` + `/release` do); paragraph-long Status:[x] narratives required; Locked design calls section at the bottom is load-bearing.

3. **Output handoff prompt** to the operator:

   ```
   External-review handoff ready. Take to Antigravity:

     1. Open .harness/PLAN.md
     2. Open .harness/transfer/plan-<ts>.md  (transfer context)
     3. Add inline comments using Antigravity's native comment UI wherever
        you want changes — task list refinement, verification specifics,
        scope adjustments, etc. The transfer context tells Gemini what
        conventions to honor + what's locked.
     4. When done commenting, ask Gemini: "apply my comments per the
        transfer context". Gemini revises the PLAN.md + writes a
        change-summary log at .harness/PLAN.diff.md.
     5. Return to Claude Code and say "plan review complete" (or run
        `/plan --resume-external-review`). Claude will diff against the
        pre-handoff snapshot and surface findings.

   Pre-handoff snapshot saved at .harness/PLAN.pre-handoff-<ts>.md.
   ```

4. **Pause the phase** — return control to the operator. The PLAN.md's Status is unchanged (still `draft`). Resume happens on the operator's next invocation.

**Resume flow** (`/plan --resume-external-review` or natural language "plan review complete"):

1. Verify expected files exist (revised PLAN.md + `.harness/PLAN.diff.md` + pre-handoff snapshot). If any missing, refuse with a clear error.
2. **Diff revised PLAN.md against pre-handoff snapshot** — read both + present unified diff. Highlight: task list changes; verification spec changes; any modifications to the `## Locked design calls` section.
3. **Read the change-summary log** — surface Gemini's per-comment narrative + the "Suggestions" section (adjacent issues Gemini noticed but didn't apply).
4. **Ask the operator**: `"Accept all changes / iterate further (another external pass) / discard the handoff entirely?"`.
   - **Accept**: clean up snapshot + transfer-context files (move to `.harness/transfer/_archive/` for audit trail; can be GC'd at 30 days). Continue to step 5 (features.json) + step 8 (Stop).
   - **Iterate**: regenerate transfer-context with updated "Recent decisions to honor" (including what was applied in the previous round); re-run handoff.
   - **Discard**: restore from pre-handoff snapshot; PLAN.md returns to its pre-handoff state; archive the failed handoff for audit; continue inline.

**Why this design**: leans on Antigravity-native primitives (inline-comment UI + Gemini-applies pattern) for the review-and-revise loop on long plans. Same mechanics as toolkit `/design` skill's external-review handoff — shared template, shared workflow shape, shared cleanup discipline. See [toolkit ADR 0004 amendment (2026-05-16)](https://github.com/alexherrero/agent-toolkit/blob/main/wiki/explanation/decisions/0004-design-skill.md) for the design rationale.

**Cross-host scope**: shipped in v2.3.1 paired with toolkit v0.8.1. The handoff target (Antigravity-Gemini) is one of the two supported hosts post-ROADMAP-item-#15 (Gemini-CLI host removal); the other supported host (Claude Code) is where the inline alternative lives.

### 5. Also update `features.json` if appropriate

If the plan introduces net-new user-visible features (as opposed to internal refactors), add entries to `.harness/features.json`:

```json
{
  "features": [
    {
      "id": "feat-auth-token-refresh",
      "description": "Access tokens auto-refresh 60s before expiry",
      "steps": ["detect near-expiry", "call refresh endpoint", "swap token atomically"],
      "passes": false
    }
  ]
}
```

**Features and tasks are not 1:1.** A feature is a user-visible capability; a task is a unit of implementation work. Scaffolding tasks (project setup, refactors, infra) produce no feature entry. A single feature may span multiple tasks. Err on the side of fewer feature entries — features are for things a user would list in a changelog, not every PR.

`passes: true` is set later, by `/review`, never by `/plan`.

### 6. Declare future state in the wiki

Dispatch the `documenter` sub-agent (full spec: [`harness/agents/documenter.md`](../agents/documenter.md)) with the newly-written `PLAN.md` and the current `wiki/how-to/` + `wiki/reference/` + `wiki/explanation/` trees. For each task that affects user-visible behavior or architecture, docsub creates or updates pending pages in the right mode dir:

- `wiki/explanation/<slug>.md` — Template 2 ("Status"), `Status: pending`, `Plan: .harness/PLAN.md#task-N`, for Feature/Subsystem pages that track pending→implemented
- `wiki/how-to/<Verb-Object>.md` — Template 4, skeleton `## Steps` to be filled from the diff at `/work`, if the task introduces a user-facing recipe
- `wiki/reference/<Name>.md` rows — add/update table rows for new commands, flags, config keys

Docsub does not touch unrelated pages, and does not preemptively edit `Home.md` / `_Sidebar.md` — those are `/release`-time concerns. If docsub returns `OPEN QUESTIONS`, resolve them before `/work` starts; an ambiguous intent statement poisons later status flips.

### 7. Offer deferred items to the GitHub Project (optional)

If `.harness/project.json` exists and `gh` is available on PATH, scan the plan's `## Out of scope` section for **intentionally-deferred** items — items the user said "not now, but worth revisiting later", *not* items explicitly rejected as non-goals. Propose one project item per intentionally-deferred entry.

**Batch the proposals into a single preview at phase end**, not interleaved mid-phase — the user confirms (or declines) the whole set in one pass, or picks which to create. No count cap: if the plan has three intentional defers, propose three. But if you're proposing more than five in one session, reconsider whether you're scope-creeping or whether some of these are actually in-scope tasks.

Preview title + body per item. On confirmation, run for each accepted item:

```bash
gh project item-create <number> --owner <owner> \
  --title "<title>" \
  --body "<body referencing .harness/PLAN.md out-of-scope entry>"
```

reading `number` and `owner` from `.harness/project.json`.

**Graceful-skip conditions** (silent, no prompt):
- `.harness/project.json` is absent.
- `gh auth status` fails or `gh` is not on PATH.
- `## Out of scope` is empty or contains only hard non-goals (no intentional defers).

Preview-and-ask is non-negotiable per [`documentation.md §GitHub Projects + Issues`](../documentation.md). No `gh project item-create` runs without explicit user confirmation. If the user declines, record nothing — their `[N]` is the decision.

### 8. Stop

**Do not start implementing.** Implementation is `/work`. A plan that bleeds into code is not a plan.

Before returning to the user:
- Confirm the plan is written to `.harness/PLAN.md`
- Append a single line to `.harness/progress.md`:
  ```
  <YYYY-MM-DD HH:MM> /plan — created plan "<title>" with N tasks
  ```
- Summarize in ≤5 bullets to the user: the goal, task count, biggest risk, next command to run (`/work` to start on task 1).

## Failure modes to avoid

- **Premature coding.** The urge to "just fix this one thing" while you're in the file. Write it as a task; handle it in `/work`.
- **Tasks too large.** If a task touches >5 files or its verification is "it works", split it.
- **Verification hand-waving.** "Manual QA" is a fallback, not a primary verification. Prefer an executable check.
- **Skipping the interview.** If you're unsure, ask. Five minutes of questions saves an hour of rework.
- **Overwriting an in-flight plan** without asking. Always check first.
- **Forgetting to update `progress.md`.** The next session won't know what happened.

## Output to the user (at end of `/plan`)

Keep it short. Example:

> Plan written to `.harness/PLAN.md`.
> - Goal: add auto-refresh of auth tokens before expiry
> - 4 tasks, smallest first
> - Biggest risk: race between refresh and in-flight requests
> - Next: `/work` to start on task 1

That's it. No essays.
