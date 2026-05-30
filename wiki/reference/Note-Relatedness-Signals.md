# Note relatedness signals reference

> [!NOTE]
> **Status:** pending
> **Plan:** `.harness/PLAN.md` task 1 (read-only `notes_link_discovery.py` relatedness engine — the signals + scoring).

The signals `notes_link_discovery.py` scores when it looks for related-but-unlinked pairs among your **personal** notes (the corpus outside `AgentMemory/` + `.obsidian/`). The audit never mutates a personal note — it surfaces candidate links for operator review (A3). Suggestions are strictly personal↔personal; an `AgentMemory/` entry is never a source or a target (DC-2).

## ⚡ Quick Reference

| Question | Answer |
|---|---|
| What runs the audit? | `harness/skills/memory/scripts/notes_link_discovery.py` (the relatedness engine + report writer). |
| How do I see suggestions? | `python3 harness/skills/memory/scripts/notes_link_discovery.py --format text` (or `--format json`). |
| Which notes are in the corpus? | Personal notes only — the Obsidian vault **excluding `AgentMemory/` + `.obsidian/`** (DC-2). |
| What is v1 relatedness based on? | TF-IDF content overlap over title + body (DC-3). Folder + date proximity are weak secondary context. |
| Does the audit ever edit a note? | No. Read-only / surface-only (DC-1). It reports + suggests; you apply the `[[links]]` by hand. |
| What is deferred? | Embedding-based semantic similarity (DC-3 follow-up); auto-creating links; any cross-link to `AgentMemory/`. |
| How do I run the report? | See [Find missing note links](../how-to/Find-Missing-Note-Links.md). |
| Related pages | [Find missing note links](../how-to/Find-Missing-Note-Links.md) |

## Signals

The personal-notes corpus has no usable graph signal — only 2/397 notes carry tags, 1/397 has a `[[wikilink]]`, and frontmatter is just `title` / `created` / `updated`. So tags, links, and frontmatter fields are **dead signals** here; v1 relatedness is content-based (DC-3).

| Signal | Role in v1 | Notes |
|---|---|---|
| TF-IDF term overlap (title + body) | Primary | _Filled by human._ (tokenization + stopword strip + IDF weighting + cosine scoring — filled from the diff at /work.) |
| Folder context | Secondary | _Filled by human._ (how same-folder proximity factors in — filled from the diff at /work.) |
| Date proximity | Secondary | _Filled by human._ (how `created` / `updated` closeness factors in — filled from the diff at /work.) |
| Existing `[[wikilinks]]` | Exclusion only | A pair already linked is never re-suggested. |
| Tags | Dead | 2/397 notes carry tags — no signal in this corpus. |
| Frontmatter fields | Dead | Only `title` / `created` / `updated` present — no signal. |

## Thresholds

_Filled by human._ (the `--min-score` similarity floor, the `--top N` shortlist cap, and any folder-vocabulary down-weighting / within-folder penalty defaults — filled from the diff at /work. 397 notes ≈ 78k pairs, so the inverted index + threshold + top-K cap keep the report a short, high-signal shortlist.)

## Related

- [Find missing note links](../how-to/Find-Missing-Note-Links.md) — the operator recipe that runs the audit and reads the report.
