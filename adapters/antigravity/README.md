# Antigravity adapter

Antigravity reads `AGENTS.md` at the project root as its primary instruction source. The harness's universal `AGENTS.md` is the authoritative entry point — no duplicate config needed.

To run a phase in Antigravity, prompt the agent with one of:

- **Setup:** "Run the setup phase from AGENTS.md — scaffold `.harness/` and `init.sh` for this project."
- **Plan:** "Run the plan phase per `harness/phases/02-plan.md`. Brief: <your brief here>."
- **Work:** "Run the work phase — implement the next unchecked task in `.harness/PLAN.md`, stop after one."
- **Review:** "Run the review phase per `harness/phases/04-review.md`. Assume the code contains bugs."
- **Release:** "Run the release phase — verify all tasks done, gates green, CI passing."
- **Bugfix:** "Run the bugfix pipeline from `harness/pipelines/bugfix.md`. Report: <bug report>."

The phase specs live in [`harness/phases/`](../../harness/phases/) — those are the single source of truth. Claude Code slash commands and Antigravity prompts both point back to them.

## Why no separate config dir?

Antigravity already honors `AGENTS.md`. A separate `.agent/` config layer would duplicate content and drift. If Antigravity ships first-class slash-command support later, we'll add it then — per the re-audit principle ([principles.md §6](../../harness/principles.md)).
