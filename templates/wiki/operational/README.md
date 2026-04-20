# Operational

How to run this project in production. The audience is an on-call engineer or deploy operator who needs to ship, observe, or recover the system quickly.

## What belongs here

- **Runbook.md** — the on-call playbook: common incidents, diagnostic steps, remediation.
- **Deployment.md** — how the project ships, which environments exist, who can deploy.
- **Observability.md** — logs, metrics, traces, dashboards, alerts.
- **Configuration.md** — env vars, feature flags, runtime config, secret sources.
- **Rollback.md** — how to undo a bad deploy without making it worse.

## What does not belong here

- **Local dev setup** → [`development/`](../development/README.md).
- **Feature design** → [`design/`](../design/README.md).
- **System architecture** → [`architecture/`](../architecture/README.md).
