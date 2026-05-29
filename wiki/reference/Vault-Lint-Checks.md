# Vault lint checks reference

> [!NOTE]
> **Status:** pending
> **Plan:** `.harness/PLAN.md` task 1 (read-only `vault_lint.py` checks engine — the check registry).

The catalog of read-only checks `vault_lint.py` runs over agent-shaped MemoryVault entries. Each check is `(entry) -> list[Finding]` where a `Finding` carries `check_id`, `severity` (`error` / `warn` / `info`), `entry_path`, `message`, and a `suggestion`. The lint never mutates the vault — it surfaces candidate fixes for operator review (A3). It targets only entries carrying the core frontmatter trio (`kind` + `status` + `created`); the operator's free-form personal notes are skipped.

## ⚡ Quick Reference

| Question | Answer |
|---|---|
| What runs the checks? | _Filled by human._ <!-- /work: link `harness/skills/memory/scripts/vault_lint.py` (the check registry + runner). --> |
| How do I see findings? | _Filled by human._ <!-- /work: `python3 .../vault_lint.py --format text` / `--format json` — confirm exact path + flags. --> |
| Which entries get linted? | Only agent-shaped entries (core frontmatter trio `kind`+`status`+`created`); free-form personal notes are skipped (DC-3). |
| Does the lint ever edit the vault? | No. Read-only / surface-only (DC-1). It reports + suggests; the operator applies. Auto-fix is deferred to V5-5. |
| How do I run a full audit report? | See [Audit the vault](../how-to/Audit-The-Vault.md). |
| Related pages | [Audit the vault](../how-to/Audit-The-Vault.md) |

## Checks

Confirm each row against the engine at /work — id, severity, what it checks, and the shape of the suggested fix.

| Check ID | Severity | What it checks | Suggested-fix shape |
|---|---|---|---|
| `frontmatter-schema` | _Filled by human._ | _Filled by human._ <!-- /work: required fields present + locked order + valid status/kind vocabulary + well-formed dates + kebab-case (reuse save.py validators). --> | _Filled by human._ |
| `wikilink-resolution` | _Filled by human._ | _Filled by human._ <!-- /work: every `[[name]]` resolves to an existing entry slug/title vault-wide. --> | _Filled by human._ |
| `supersede-integrity` | _Filled by human._ | _Filled by human._ <!-- /work: `supersedes:` resolves to a real entry + the referenced entry's status reflects being superseded (no dangling/contradictory chains). --> | _Filled by human._ |
| `schema-drift` | _Filled by human._ <!-- /work: DC-5 — unknown status/kind = warn, not error. --> | _Filled by human._ <!-- /work: unknown/deprecated frontmatter keys or kinds not in the current vocabulary. --> | _Filled by human._ |

## Related

- [Audit the vault](../how-to/Audit-The-Vault.md) — the operator recipe that runs these checks and reads the report.
