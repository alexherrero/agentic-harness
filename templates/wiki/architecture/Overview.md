# Overview

A one-page map of how this system is built. The `/setup` phase seeds this page from the top-level repo layout, entry points, and any major subsystem boundaries it can identify; a human should refine it.

## ⚡ Quick Reference

| Question | Answer |
|---|---|
| Language / runtime | _Populated by `/setup` from manifests._ |
| Entry points | _Populated by `/setup`._ |
| Data stores | _Populated by `/setup` if any are detected._ |
| External dependencies | _Populated by `/setup`._ |

## Components

_A short list of the major components — services, packages, workers, apps — and what each one is responsible for. Populated by `/setup` from the repo layout._

## Data flow

_How requests or events move through the system. A diagram (ASCII or Mermaid) is usually clearer than prose here._

```
<placeholder: populate with an ASCII or Mermaid diagram of the request/event flow>
```

## Entry points

_Where execution starts — CLI commands, HTTP routes, queue consumers, cron triggers. File references with `path:line` links._

## Key decisions

_Non-obvious architectural choices. Each should have a corresponding ADR under `decisions/`; this section is the index._
