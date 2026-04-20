# Runbook

The on-call playbook for this project. Covers common incidents, diagnostic steps, and remediation. The `/setup` phase seeds known incident patterns from the CI / deploy / observability config; new entries accrue as incidents occur.

## ⚡ Quick Reference

| Situation | First step |
|---|---|
| Service is down | _Populated by `/setup` based on deploy surface._ |
| Deploy failed | _Populated by `/setup` based on CI config._ |
| Database / migration issue | _Populated by `/setup` if a migration surface exists._ |

## Common incidents

_One section per recurring incident. Each section: symptoms → diagnosis → remediation → post-incident notes. Empty until the first incident lands._

## Health checks

_How to verify the system is healthy. URLs, commands, dashboards. Filled by `/setup` if health-check surface exists._

## Escalation

_Who to page, how to reach them, what information to include. Filled by the human maintaining this page — not auto-populated._
