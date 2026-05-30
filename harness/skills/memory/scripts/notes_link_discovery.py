#!/usr/bin/env python3
"""notes_link_discovery — read-only "missing link" audit for personal notes (V4 #43).

The complement to `vault_lint` (#33). Where vault_lint validates the *agent-shaped*
`AgentMemory/` entries and **skips** the operator's free-form personal notes, this
module audits **only those skipped personal notes** for *missing connections between
them*: "these two notes look related but aren't `[[linked]]` — consider connecting
them."

The corpus is the enclosing Obsidian vault **excluding `AgentMemory/` + `.obsidian/`**
(reusing `vault_lint._obsidian_root`). The exclusion **is** the domain boundary
(DC-2): suggestions are inherently personal↔personal — a personal note is never
related-linked to an `AgentMemory/` entry, because `AgentMemory/` is never in the
corpus as either source or target.

Relatedness is **content-based** (DC-3): the operator's notes have ~no tags, ~no
wikilinks, and only `title`/`created`/`updated` frontmatter, so those are dead
signals. v1 = hand-rolled **TF-IDF over title+body** + an **inverted index** (only
compare notes sharing terms) + **cosine similarity**, surfacing related-but-unlinked
pairs above a threshold. Folder + date proximity are available as weak secondary
context. (Task 3 adds an embedding signal alongside this lexical one.)

**Strictly read-only** (DC-1) — opens personal notes for read only, never edits one
and never auto-creates a link. The `report` mode writes a single operator-review
file to `AgentMemory/_meta/` (agent-controlled output), never to a personal note.
The operator applies suggestions by hand (A3 — these are *his* notes).

Stdlib-only (no sklearn — hand-rolled TF-IDF), cross-platform.

CLI:
    python3 notes_link_discovery.py [--vault PATH] [--format json|text]
                                    [--top N] [--min-score X]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import vault_lint  # noqa: E402  (reuse _obsidian_root + parse_frontmatter — same skill dir)

# Directories that are NOT operator personal notes — excluded from the corpus.
# `AgentMemory/` is the agent's own vault (the hard domain boundary, DC-2);
# `.obsidian/` is Obsidian's config; `.trash` is Obsidian's soft-delete bin.
_EXCLUDE_DIRS = frozenset({"AgentMemory", ".obsidian", ".trash", ".git"})

# Defaults — tuned against the live 397-note dogfood (task 2).
_DEFAULT_MIN_SCORE = 0.18
_DEFAULT_TOP = 40
# A term must appear in at least this many notes to be indexed at all (drops
# per-note typos/unique noise) but fewer than this fraction of the corpus (drops
# ubiquitous boilerplate the IDF would already down-weight — a hard cap keeps the
# inverted-index postings short so the pair scan stays bounded).
_MIN_DF = 2
_MAX_DF_RATIO = 0.5

# Tokenizer: lowercase alphanumeric runs of >= 3 chars (drops "a", "of", digits-
# only noise like years bleak less). Apostrophes are split (don't -> don, t-drop).
_TOKEN_RE = re.compile(r"[a-z][a-z0-9]{2,}")

# A compact English stopword set + Markdown/Obsidian boilerplate. Hand-rolled
# (stdlib-only, no nltk). IDF already down-weights common terms; this just keeps
# the inverted index from being dominated by function words.
_STOPWORDS = frozenset("""
the and that have for not with you this but his from they she will would there
their what about which when make can like time just him know take people into
year your good some could them than then now look only come its over think also
back after use two how our work first well way even new want because any these
give day most us was are were has had been being who why all out off too very
get got going one let going lets per via vs etc eg ie aka onto upon within
without across among around before behind below beneath beside between beyond
during except inside near since toward under until upon while https http www com
org net html md png jpg jpeg gif note notes link links page see also ref
""".split())


# -----------------------------------------------------------------------------
# Data shapes
# -----------------------------------------------------------------------------

@dataclass
class Note:
    """A parsed personal note (corpus member)."""
    path: Path
    rel: str               # POSIX path relative to the Obsidian root (no .md)
    title: str
    folder: str            # top-level folder under the root ("" if at root)
    created: str
    updated: str
    body: str
    links: set = field(default_factory=set)   # resolved wikilink targets (stems + rel paths)
    tf: dict = field(default_factory=dict)     # term -> raw count (title double-weighted)


@dataclass
class Suggestion:
    a_rel: str
    b_rel: str
    a_title: str
    b_title: str
    a_folder: str
    b_folder: str
    score: float
    shared_terms: list      # top distinctive shared terms, by contribution
    same_folder: bool

    def to_dict(self) -> dict:
        return {
            "a": self.a_rel,
            "b": self.b_rel,
            "a_title": self.a_title,
            "b_title": self.b_title,
            "a_folder": self.a_folder,
            "b_folder": self.b_folder,
            "score": round(self.score, 4),
            "shared_terms": self.shared_terms,
            "same_folder": self.same_folder,
            "signal": "tfidf",
        }


# -----------------------------------------------------------------------------
# Corpus build
# -----------------------------------------------------------------------------

def _tokenize(text: str) -> list:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _title_from(path: Path, fm: Optional[dict]) -> str:
    if fm:
        t = (fm.get("title") or "").strip().strip("'\"")
        if t:
            return t
    return path.stem


def _resolve_link(target: str) -> tuple:
    """Normalize a raw `[[target]]` to (stem, rel-or-None) for self-link matching.
    Strips alias, anchor, and a trailing .md."""
    t = target.split("|", 1)[0].split("#", 1)[0].split("^", 1)[0].strip()
    t = t.strip("/")
    if t.endswith(".md"):
        t = t[:-3]
    if not t:
        return "", None
    if "/" in t:
        return t.rsplit("/", 1)[-1], t
    return t, None


def build_corpus(vault: Path) -> list:
    """Walk the Obsidian root, parse every personal note (excluding AgentMemory/
    + Obsidian config), return a list[Note]. Read-only."""
    root = vault_lint._obsidian_root(Path(vault))
    notes = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded dirs in-place so os.walk doesn't descend into them.
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            p = Path(dirpath) / fn
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm, _order, body = vault_lint.parse_frontmatter(text)
            try:
                rel = p.relative_to(root).with_suffix("").as_posix()
            except ValueError:
                continue
            parts = rel.split("/")
            folder = parts[0] if len(parts) > 1 else ""
            links = set()
            for m in vault_lint._WIKILINK_RE.finditer(body):
                stem, relpath = _resolve_link(m.group(1))
                if stem:
                    links.add(stem)
                if relpath:
                    links.add(relpath)
            note = Note(
                path=p,
                rel=rel,
                title=_title_from(p, fm),
                folder=folder,
                created=(fm.get("created", "").strip() if fm else ""),
                updated=(fm.get("updated", "").strip() if fm else ""),
                body=body,
                links=links,
            )
            # Title terms count double — a shared title term is a stronger signal
            # than a shared body term.
            counts = defaultdict(int)
            for tok in _tokenize(note.title):
                counts[tok] += 2
            for tok in _tokenize(note.body):
                counts[tok] += 1
            note.tf = dict(counts)
            notes.append(note)
    return notes


# -----------------------------------------------------------------------------
# TF-IDF + inverted index + cosine
# -----------------------------------------------------------------------------

@dataclass
class Model:
    notes: list                      # list[Note]
    idf: dict                        # term -> idf weight
    postings: dict                   # term -> list[int] (note indices)
    vectors: list                    # list[dict] term -> tf-idf weight (l2-normalized)
    norms: list                      # parallel l2 norms (== 1.0 unless degenerate)


def build_model(notes: list, *, min_df: int = _MIN_DF,
                max_df_ratio: float = _MAX_DF_RATIO) -> Model:
    n = len(notes)
    df = defaultdict(int)
    for note in notes:
        for term in note.tf:
            df[term] += 1
    # The boilerplate cap is `max_df_ratio * n`. Apply it ONLY when it sits above
    # the min_df floor; below that (corpus smaller than min_df/max_df_ratio notes)
    # the band [min_df, ratio_cap] would collapse to a single point (or invert),
    # silently deleting the very distinctive term a genuine pair shares — e.g. at
    # n=3 a term that a third note also mentions (df=3) would be dropped and the
    # vocab can collapse to empty. In that small-corpus regime there's not enough
    # evidence to call a term "too common", so disable the cap and let IDF do the
    # down-weighting. (Do NOT floor with max(min_df, …): that's what inverted the
    # band.)
    ratio_cap = int(max_df_ratio * n) if n else 0
    max_df = ratio_cap if ratio_cap >= min_df else n
    # Keep terms in the document-frequency band [min_df, max_df]. A term shared by
    # only one note can't connect a pair; a near-ubiquitous term is boilerplate.
    vocab = {t for t, c in df.items() if c >= min_df and c <= max_df}
    idf = {t: math.log((n + 1) / (df[t] + 1)) + 1.0 for t in vocab}

    postings = defaultdict(list)
    vectors = []
    norms = []
    for i, note in enumerate(notes):
        vec = {}
        for term, raw in note.tf.items():
            if term not in vocab:
                continue
            # sublinear tf damps long notes dominating on sheer repetition.
            w = (1.0 + math.log(raw)) * idf[term]
            if w > 0:
                vec[term] = w
        norm = math.sqrt(sum(w * w for w in vec.values()))
        if norm > 0:
            for term in vec:
                vec[term] /= norm
        for term in vec:
            postings[term].append(i)
        vectors.append(vec)
        norms.append(norm)
    return Model(notes=notes, idf=idf, postings=dict(postings),
                 vectors=vectors, norms=norms)


def _already_linked(a: Note, b: Note) -> bool:
    """True if either note already wikilinks the other (by stem or rel path).

    Known limitation: a bare `[[stem]]` link is matched by stem, so when two
    distinct notes share a filename stem (`Work/daily`, `Journal/daily`) a bare
    link to one can falsely suppress a suggestion to the other. This mirrors
    Obsidian's own bare-link ambiguity, costs at most one missed *suggestion*
    (never a wrong write — the tool is suggest-only), and is near-impossible in
    this corpus (≈1/397 notes carry any wikilink), so it's accepted, not guarded."""
    a_stem = a.path.stem
    b_stem = b.path.stem
    if b_stem in a.links or b.rel in a.links:
        return True
    if a_stem in b.links or a.rel in b.links:
        return True
    return False


def score_pairs(model: Model, *, min_score: float = _DEFAULT_MIN_SCORE,
                top: int = _DEFAULT_TOP) -> list:
    """Cosine-score every candidate pair (sharing >= 1 indexed term), drop
    already-linked + below-threshold pairs, return the top-K Suggestions."""
    notes = model.notes
    vectors = model.vectors
    # Accumulate dot products only over pairs that share a posting (inverted
    # index) — never the full O(n^2) cross product.
    dot = defaultdict(float)
    contrib = defaultdict(lambda: defaultdict(float))  # (i,j) -> term -> contribution
    for term, plist in model.postings.items():
        if len(plist) < 2:
            continue
        for x in range(len(plist)):
            i = plist[x]
            wi = vectors[i].get(term, 0.0)
            if wi == 0.0:
                continue
            for y in range(x + 1, len(plist)):
                j = plist[y]
                wj = vectors[j].get(term, 0.0)
                if wj == 0.0:
                    continue
                c = wi * wj
                key = (i, j)
                dot[key] += c
                contrib[key][term] += c

    suggestions = []
    for (i, j), sim in dot.items():
        if sim < min_score:
            continue
        a, b = notes[i], notes[j]
        if _already_linked(a, b):
            continue
        shared = sorted(contrib[(i, j)].items(), key=lambda kv: kv[1], reverse=True)
        shared_terms = [t for t, _ in shared[:6]]
        suggestions.append(Suggestion(
            a_rel=a.rel, b_rel=b.rel,
            a_title=a.title, b_title=b.title,
            a_folder=a.folder, b_folder=b.folder,
            score=sim, shared_terms=shared_terms,
            same_folder=(a.folder == b.folder and a.folder != ""),
        ))
    # Highest score first; stable tiebreak on the note paths for determinism.
    suggestions.sort(key=lambda s: (-s.score, s.a_rel, s.b_rel))
    if top and top > 0:
        suggestions = suggestions[:top]
    return suggestions


def discover(vault: Path, *, min_score: float = _DEFAULT_MIN_SCORE,
             top: int = _DEFAULT_TOP) -> tuple:
    """End-to-end: corpus -> model -> ranked suggestions. Returns (notes, suggestions)."""
    notes = build_corpus(vault)
    model = build_model(notes)
    suggestions = score_pairs(model, min_score=min_score, top=top)
    return notes, suggestions


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _render_text(notes: list, suggestions: list) -> str:
    out = [
        f"notes-link-discovery: {len(suggestions)} related-but-unlinked pair(s) "
        f"across {len(notes)} personal notes",
        "",
    ]
    for s in suggestions:
        a = f"{s.a_folder + '/' if s.a_folder else ''}{s.a_title}"
        b = f"{s.b_folder + '/' if s.b_folder else ''}{s.b_title}"
        out.append(f"  [{s.score:.3f}] {a}  <->  {b}")
        out.append(f"      shared: {', '.join(s.shared_terms)}")
    if not suggestions:
        out.append("  no related-but-unlinked pairs above threshold.")
    return "\n".join(out) + "\n"


def main(argv: Optional[list] = None) -> int:
    # Windows stdout defaults to cp1252, which can't encode some glyphs. Force
    # UTF-8 best-effort so the CLI never UnicodeEncodeErrors.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    p = argparse.ArgumentParser(
        prog="notes_link_discovery",
        description="Read-only missing-link audit for personal notes (V4 #43).")
    p.add_argument("--vault", default=None, help="vault root (else MEMORY_VAULT_PATH)")
    p.add_argument("--format", choices=("json", "text"), default="text")
    p.add_argument("--top", type=int, default=_DEFAULT_TOP, help="max suggestions (0 = all)")
    p.add_argument("--min-score", type=float, default=_DEFAULT_MIN_SCORE,
                   help="cosine-similarity threshold")
    args = p.parse_args(argv)
    try:
        vault = vault_lint._resolve_vault(args.vault)
    except FileNotFoundError as e:
        print(f"notes_link_discovery: {e}", file=sys.stderr)
        return 2
    if not vault.is_dir():
        print(f"notes_link_discovery: vault not found: {vault}", file=sys.stderr)
        return 2

    notes, suggestions = discover(vault, min_score=args.min_score, top=args.top)

    if args.format == "json":
        print(json.dumps({
            "notes": len(notes),
            "suggestions": [s.to_dict() for s in suggestions],
        }, indent=2, ensure_ascii=False))
    else:
        print(_render_text(notes, suggestions), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
