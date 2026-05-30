# How to find missing links among your personal notes

> [!NOTE]
> **Status:** pending
> **Plan:** `.harness/PLAN.md` tasks 1 (read-only `notes_link_discovery.py` relatedness engine) + 2 (`report` mode → operator-review suggestion report).
> **Goal:** Run the read-only personal-notes link-discovery audit, read the ranked "these two notes look related but aren't linked" report it writes under `_meta/`, and add the suggested `[[wikilinks]]` by hand in Obsidian — the audit never edits a personal note.
> **Prereqs:** agentm v4.10.0+ (ships V4 #43), `python3` on `PATH`, and a reachable Obsidian vault (`MEMORY_VAULT_PATH` set, or pass `--vault PATH`). The audit reads only; it surfaces candidate links for you to review and apply.

This audit is the complement to [Audit the vault](Audit-The-Vault) — that one lints your agent-shaped `AgentMemory/` entries; this one looks at your ~397 **personal** notes (the ones outside `AgentMemory/`) and surfaces pairs that read as related but have no `[[wikilink]]` between them. It is strictly **personal↔personal**: it never suggests linking a personal note to an `AgentMemory/` entry.

## Steps

1. **Preview the suggestions (optional).** Run the audit and print the related-but-unlinked pairs to your terminal — `text` for skimming, `json` for piping:

   ```bash
   python3 harness/skills/memory/scripts/notes_link_discovery.py --format text
   python3 harness/skills/memory/scripts/notes_link_discovery.py --format json
   ```

   _Filled by human._ (flag behavior — `--top N`, `--min-score X`, `--vault PATH` — filled from the diff at /work.)

2. **Write the suggestion report.** _Filled by human._ (the `report` mode invocation + the `AgentMemory/_meta/notes-links-<YYYY-MM-DD>.md` output path + the one-line summary it prints — filled from the diff at /work.) The report is the **only** thing the audit writes — it never touches a personal note.

3. **Read the report.** Open `<vault>/AgentMemory/_meta/notes-links-<YYYY-MM-DD>.md`. _Filled by human._ (how suggestions are grouped + what each entry carries — the two notes, the shared distinctive terms, the score, and the ready-to-paste `[[wikilink]]` for both directions — filled from the diff at /work.)

4. **Add the links by hand.** Open the suggested notes in Obsidian and paste the `[[wikilink]]` where it reads naturally. The audit applies nothing — every suggestion is advisory and operator-gated (A3 — these are **your** notes). Re-run step 1 to confirm an applied pair drops off the list.

For what each relatedness signal means and how the thresholds are tuned, see [Note relatedness signals](Note-Relatedness-Signals).

## Related

- [Note relatedness signals reference](Note-Relatedness-Signals) — the signals + thresholds the audit scores on (v1 = TF-IDF content overlap).
- [Audit the vault](Audit-The-Vault) — the complementary recipe that lints your agent-shaped `AgentMemory/` entries.
