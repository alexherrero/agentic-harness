# Architecture

How the system is built: subsystems, data flow, and decisions worth knowing. The audience is a contributor (human or agent) who needs to understand structure before making a change.

## What belongs here

- **Overview.md** — one-page system map: components, data flow, entry points.
- **subsystems/`<name>`.md** — one page per subsystem. Uses the **Status** template when the subsystem is new or materially changing. Maintained by the `documenter` sub-agent.
- **Data-Model.md** — core data shapes and persistence.
- **Integrations.md** — external services, APIs, and dependencies.
- **decisions/`<NNNN>`-`<slug>`.md** — Architecture Decision Records. Uses the **ADR** template. One file per decision, numbered sequentially.

## What does not belong here

- **Product and UX intent** → [`design/`](../design/README.md).
- **Ops and deploy** → [`operational/`](../operational/README.md).
- **Local dev** → [`development/`](../development/README.md).

## ADRs

Decisions live under `decisions/` as `<NNNN>-<slug>.md` (e.g. `0001-postgres-for-persistence.md`). Use Template 3 from the [wiki convention](../README.md#template-3--adr). ADRs are append-only: when a decision is superseded, mark its status `superseded-by-<NNNN>` and record the new decision as a fresh ADR.
