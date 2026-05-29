# How to audit the MemoryVault for off-spec entries

> [!NOTE]
> **Status:** pending
> **Plan:** `.harness/PLAN.md` tasks 1 (read-only `vault_lint.py` checks engine) + 2 (`audit` mode → operator-review report).
> **Goal:** Run the read-only vault lint, read the categorized report it writes under `_meta/`, and apply the suggested fixes by hand — the lint never edits the vault.
> **Prereqs:** agentm v4.9.0+ (ships V4 #33), `python3` on `PATH`, and a reachable vault (`MEMORY_VAULT_PATH`). The lint reads only; it surfaces candidate fixes for you to review and apply.

_Filled by human._ <!-- /work: one-paragraph framing of the read-only audit flow — run the lint, skim the report, apply fixes at your discretion. -->

## Steps

1. _Filled by human._ <!-- /work: run the lint over the resolved vault, e.g. `python3 harness/skills/memory/scripts/vault_lint.py --format text` (confirm the invocation + scope flag against the engine). -->
2. _Filled by human._ <!-- /work: run `vault_lint.py audit` to write the categorized operator-review report to `<vault>/_meta/vault-lint-<YYYY-MM-DD>.md`; note the leading summary line. -->
3. _Filled by human._ <!-- /work: read the report — findings grouped by severity (error / warn / info) then area, each with a suggested fix phrased for a human. -->
4. _Filled by human._ <!-- /work: apply the suggested fixes by hand. The lint applies nothing — every fix is operator-gated (A3). -->

## Related

- [Vault lint checks reference](Vault-Lint-Checks) — the check catalog: id / severity / what each checks / suggested-fix shape.
