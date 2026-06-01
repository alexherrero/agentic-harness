# Feature: auto-orchestration — the memory push-surface

> [!NOTE]
> **Status:** implemented

Turn the Agent M memory skills from a *pull surface* into a *push surface*. Until now you invoked recall, reflect, discover-skills, adapt-skills, and the watchlist by hand. With auto-orchestration the system surfaces pending state when you open a session, fires the right memory chains during idle time, and reflects + refreshes at the harness phase boundaries — without you running anything. It never blocks a session, never nags, and never acts on its own: it is plumbing and nudges, and every actual adoption or write stays operator-gated.

## ⚡ Quick Reference

| Question | Answer |
|---|---|
| What does it add? | A SessionStart pending-state briefing (with two nudges), a bounded idle-time memory chain, and phase-boundary reflect + skill-refresh dispatches. |
| What triggers the briefing? | SessionStart, but only when pending state has shifted since you last saw it and the cooldown allows. |
| What does the briefing report? | `_inbox/` count over threshold · `_skill-watchlist/` pending-HIGH count · `_idea-incubator/` entries pending research · GC-eligible idea-ledger items · plus two nudges (recurring ideas worth promoting · stale `promoted` watchlist entries). |
| What does the idle chain run? | reflect-corpus → discover-skills cadence-check → adapt-skills Pass-1 (staging candidates), cooldown-gated. Pass-2 evaluation is deliberately not a hook step. |
| When does phase-integration fire? | After `/work` (reflect the finished session) and after `/release` (index + discover skills), via the phase specs. |
| How do I tune it? | Edit the operator config — see [Tune auto-orchestration](Tune-Auto-Orchestration). |
| Where do the keys live? | [Auto-orchestration config](Auto-Orchestration-Config). |
| Can it adopt a skill on its own? | No. It proposes and nudges; adoption and any write outside A3 stay operator-gated. |

## Intent

The memory skills were already powerful, but you had to remember to use them. Pending work piled up unseen — an inbox over threshold, watchlist patterns waiting for review, incubator ideas that never got researched, stale idea-ledger entries that should have been collected. The skills sat there until you thought to ask.

Auto-orchestration closes that gap on three surfaces. **At session start** the briefing tells you what needs attention — *"3 watchlist patterns to review · inbox over threshold · 2 incubator ideas pending research"* — in one tight block, plus two nudges: ideas you keep having (worth promoting) and watchlist patterns you said you'd author but haven't. **During idle time** the discover→adapt chain runs itself in bounded passes, staging candidates so you stop hand-invoking `adapt-skills`. **At the phase boundaries** a finished `/work` session gets reflected and a finished `/release` refreshes the skill surfaces — without you running `reflect` or `index-skills` by hand.

The posture is the whole point. Every surface is non-blocking and graceful-skips on any failure, so a broken script never fails your session boot or wedges a phase. Cooldowns and a "only fire when state has shifted since last shown" guard keep the briefing from nagging. And nothing is autonomous — the system proposes and nudges, but every adoption, every fork, every write outside the A3 permeable boundary still waits for you.

## Design

Three cooperating push surfaces over one shared state + config core, deliberately separated so the deterministic plumbing stays testable and the nudges stay operator-gated.

```
SessionStart ──▶ briefing generator ──▶ 1–3 line block + nudges (only if shifted + cooled)
                          │
/work · /release ──▶ phase-dispatch ──▶ post-work reflect / post-release index + discover
                          │
memory-reflect-idle ──▶ idle chain: reflect-corpus → discover-skills → adapt Pass-1 (stage candidates)
                          │
                          │ all read toggles/thresholds/cooldowns, write last-fire timestamps
                          ▼
   <vault>/_meta/auto-orchestration-state.json          (last_fire + last_shown snapshot)
   <vault>/personal-private/auto-orchestration-config.md (operator-tunable, auto-seeded)
```

The load-bearing design calls, and why each is what it is:

- **DC-1 — build mechanism is hook/file-based and cross-host.** It extends the existing `memory-reflect-idle` and SessionStart hooks plus file-based state and config — not the Anthropic Workflow SDK primitive, which is Claude-tier-gated and would lose Antigravity parity. The Workflow hybrid is a post-V4 research follow-up.
- **DC-2 — full scope shipped.** All seven sub-items landed across six commits: the state + config core, the briefing, SessionStart wiring, the idle chain, phase-integration auto-dispatch, and both nudges (promote-suggest + stale-promotion). Nothing from the original surface is deferred.
- **DC-3 — everything is agentm-native.** The scripts, the SessionStart/idle hooks, and the phase wiring all live in `agentm` (`harness/skills/memory/scripts/`, `harness/hooks/`, `harness/phases/`). There is no crickets crossover and no paired release — the push-surface ships entirely from the harness.
- **Pass-2 is not a hook step (Option A).** A hook fires outside the agent loop and cannot dispatch a sub-agent, so the idle chain stops after staging Pass-1 candidates and surfaces the staged count. The `adapt-evaluator` (Pass-2) hand-off happens via phase-dispatch / nudge, where sub-agent dispatch is legitimate and operator-gated.
- **Never blocks, never nags.** Every surface is non-blocking and exits clean on any failure. Cooldowns plus the shifted-since-last-shown check guard notification fatigue; the right defaults calibrate under the real-use dogfood.
- **A3 permeable boundary.** The system proposes and nudges; it never auto-adopts a skill, never auto-forks to the toolkit (adapt-don't-import is inviolable), and never writes outside the A3 contract without an operator gate.

The idle chain is bounded by construction: each step no-ops when its input is empty, reflect-corpus caps at five unseen sessions per pass (`--batch-size 5 --max-batches 1`), adapt-skills runs `--limit 3`, the whole chain is cooldown-gated through the state file, and a `--dry-run` mode keeps it testable. Re-running inside a cooldown window is a no-op. Because a fired chain can outrun the 30s SessionStart hook timeout, the driver is launched detached and its results surface on the *next* session's briefing.

## Implementation

All agentm-native. The state + config core is one stdlib-only module the other surfaces import; each surface is its own driver with a `--dry-run` seam and a `never raises` contract.

| Concern | Where |
|---|---|
| State read/write · cooldowns · shifted-since-last-shown guard · config parse + idempotent seed | `harness/skills/memory/scripts/auto_orchestration.py` |
| SessionStart briefing + the two nudges | `harness/skills/memory/scripts/orchestration_briefing.py` |
| Idle-time chain (reflect-corpus → discover → adapt Pass-1) | `harness/skills/memory/scripts/orchestration_idle.py` |
| Phase-integration dispatch (post-work reflect · post-release refresh) | `harness/skills/memory/scripts/orchestration_phase.py` |
| Idle-chain launch (detached) | `harness/hooks/memory-reflect-idle/hook.md` |
| Briefing attach point | `harness/hooks/memory-recall-session-start/` |
| Phase wiring | `harness/phases/03-work.md` §9b + `harness/phases/05-release.md` §9b → `harness_memory.py phase-dispatch` |

## Notes

- **Notification fatigue** is the named risk. The mitigation — cooldowns, shifted-since-last-shown, operator-tunable thresholds — only calibrates under real use, so the real-use dogfood on the operator's own vault is the primary acceptance gate, not deterministic tests alone.
- **Idle-chain cost** is bounded by `--max-batches 1` / `--limit 3` / cadence-checks and per-step no-ops. If a step proves too costly to auto-fire, it gets demoted to a SessionStart "you could run X" nudge.
- **The Anthropic Workflow hybrid** stays a post-V4 research follow-up (DC-1) — the shipped surface is deliberately hook/file-based so it keeps Antigravity parity.

## Related

- [Tune auto-orchestration](Tune-Auto-Orchestration) — the operator recipe for thresholds, cooldowns, and chain toggles.
- [Auto-orchestration config](Auto-Orchestration-Config) — the config-key and state-file reference.
- [Use auto-context in harness phases](Use-Auto-Context-In-Harness-Phases) — the phase-boundary pull surface this push-surface complements.
- [How the pieces fit](How-The-Pieces-Fit) — where the memory hooks sit in the phase/adapter model.
