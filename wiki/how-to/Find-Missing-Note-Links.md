# How to find missing links among your personal notes

> [!NOTE]
> **Status:** implemented
> **Goal:** Run the read-only personal-notes link-discovery audit, read the ranked "these two notes look related but aren't linked" report it writes under `_meta/`, and add the suggested `[[wikilinks]]` by hand in Obsidian — the audit never edits a personal note.
> **Prereqs:** agentm v4.10.0+ (ships V4 #43), `python3` on `PATH`, and a reachable Obsidian vault (`MEMORY_VAULT_PATH` set, or pass `--vault PATH`). The embedding signal additionally needs the `sentence-transformers` package; without it the audit runs TF-IDF-only.

This audit is the complement to [Audit the vault](Audit-The-Vault) — that one lints your agent-shaped `AgentMemory/` entries; this one looks at your **personal** notes (the ones outside `AgentMemory/`) and surfaces pairs that read as related but have no `[[wikilink]]` between them. It is strictly **personal↔personal**: it never suggests linking a personal note to an `AgentMemory/` entry.

## Steps

1. **Preview the suggestions (optional).** Run the audit and print the related-but-unlinked pairs to your terminal — `text` for skimming, `json` for piping:

   ```bash
   python3 harness/skills/memory/scripts/notes_link_discovery.py --format text
   python3 harness/skills/memory/scripts/notes_link_discovery.py --format json
   ```

   Tuning flags: `--top N` caps the shortlist (default 40; `0` = all), `--min-score X` sets the TF-IDF cosine floor (default `0.18`), and `--vault PATH` points at a specific Obsidian root when `MEMORY_VAULT_PATH` isn't set. The corpus is every `.md` under the Obsidian root **except** `AgentMemory/`, `.obsidian/`, `.trash`, and `.git`.

2. **Add the semantic signal (optional but recommended).** Pass `--embeddings` to run a second relatedness pass that catches related notes which *don't share surface vocabulary* — including the same note in two languages:

   ```bash
   python3 harness/skills/memory/scripts/notes_link_discovery.py --embeddings --format text
   ```

   This embeds each note with the local BGE model and caches the vectors at `<vault>/_meta/notes-embeddings.json` (content-hash keyed, so re-runs only re-embed changed notes — the first run is slow, later runs are fast). `--embed-min-score X` sets the embedding cosine floor (default `0.70`). If `sentence-transformers` isn't installed the audit prints a one-line notice and falls back to TF-IDF-only — never an error.

3. **Write the suggestion report.** Add `--report` to write the operator-review markdown instead of printing:

   ```bash
   python3 harness/skills/memory/scripts/notes_link_discovery.py --report --embeddings
   ```

   It writes `AgentMemory/_meta/notes-links-<YYYY-MM-DD>.md` and prints a one-line summary (`N TF-IDF + M embedding-only suggestion(s) across K notes -> <path>`). The report is the **only** thing the audit writes — it refuses any `--out` path that lands outside the agent-controlled vault or onto a personal note, so it can never overwrite a note.

4. **Read the report.** Open `<vault>/AgentMemory/_meta/notes-links-<YYYY-MM-DD>.md`. It leads with a summary, then a **Shared-vocabulary links (TF-IDF)** section — each entry carries the two notes (folder/title), the top shared distinctive terms (the *why*), the score, and a ready-to-paste `[[wikilink]]` for both directions; pairs the embedding signal also agrees on are flagged `✓ also semantically related`. When `--embeddings` ran, a second **Semantically related (embedding signal — TF-IDF missed these)** section lists the pairs found only by meaning. Names containing `[`/`]`/`|`/`#` (e.g. bracketed-date meeting notes) can't be valid `[[wikilinks]]`, so those show a "link via Obsidian's `[[` picker" hint instead of a broken link.

5. **Add the links by hand.** Open the suggested notes in Obsidian and paste the `[[wikilink]]` where it reads naturally. The audit applies nothing — every suggestion is advisory and operator-gated (A3 — these are **your** notes). Re-run step 1 to confirm an applied pair drops off the list.

For what each relatedness signal means and how the thresholds are tuned, see [Note relatedness signals](Note-Relatedness-Signals).

## Related

- [Note relatedness signals reference](Note-Relatedness-Signals) — the two signals (TF-IDF + embedding) and their thresholds.
- [Audit the vault](Audit-The-Vault) — the complementary recipe that lints your agent-shaped `AgentMemory/` entries.
