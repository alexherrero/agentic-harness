---
name: harness-setup
description: First-time project scaffold for agentic-harness. Populates init.sh with real commands, verifies it boots, seeds AGENTS.md, features.json, and the wiki/ scaffold. Run once per project. Prefixed harness- to avoid collision with Codex built-ins. Does not plan — planning is the harness-plan skill.
---

# harness-setup skill

Run the **setup** phase of agentic-harness. Full spec: [`harness/phases/01-setup.md`](../../../../harness/phases/01-setup.md). Read it and follow it.

## Non-negotiable constraints

1. **Inventory before interviewing.** Read `README.md`, `package.json`/`go.mod`/etc., `.github/workflows/`, any existing `AGENTS.md`. Ask only what the inventory can't answer.
2. **Populate `.harness/init.sh` with real commands, not guesses.** If unsure, ask. A broken `init.sh` breaks every later phase.
3. **Verify `init.sh` boots cleanly** — run it and confirm exit 0 before finishing.
4. **Do not invent features** for `.harness/features.json`. Empty is fine.
5. **Merge, don't overwrite** existing `AGENTS.md`. It may contain project-specific content.
6. **No planning.** `harness-setup` is pure scaffolding. Planning is the `harness-plan` skill.
7. **Dispatch the `documenter` subagent** after boot verification to populate the `wiki/` seed pages (`Getting-Started`, `Runbook`, `Product-Intent`, `Overview`, `Home`, `_Sidebar`) from the inventory and interview. Resolve any `OPEN QUESTIONS` before finishing.
8. **Offer GitHub Project creation** (user-scoped, `gh project create --owner @me`) — ask first. If accepted, write `.harness/project.json`.

Start by reading what's in the project now, then interview briefly on anything the inventory didn't settle.
