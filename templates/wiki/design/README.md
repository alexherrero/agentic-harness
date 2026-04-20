# Design

Product and UX intent: what this project does for its users and why. The audience is a contributor who needs to understand the user-facing rationale before touching behavior.

## What belongs here

- **Product-Intent.md** — what this project is, who it's for, what problem it solves.
- **User-Flows.md** — key user journeys with screenshots or sequence diagrams.
- **features/`<slug>`.md** — one page per user-visible feature. Uses the **Status** template (`pending → implemented → deprecated`). Maintained by the `documenter` sub-agent across `/plan`, `/work`, and `/release`.
- **Open-Questions.md** — design questions still unresolved.

## What does not belong here

- **Internal subsystems and architecture** → [`architecture/`](../architecture/README.md).
- **Dev environment setup** → [`development/`](../development/README.md).
- **Ops / runbook** → [`operational/`](../operational/README.md).

## Feature pages

Features live under `features/` and use Template 2 ("Status") from the [wiki convention](../README.md#template-2--status-extension). The status callout at the top (`pending` / `implemented` / `deprecated`) is how `documenter` tracks the lifecycle.
