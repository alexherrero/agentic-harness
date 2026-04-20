#!/usr/bin/env bash
# test-install.sh — dedicated installer-boundary test.
#
# Asserts the invariant that `install.sh` copies ONLY from
# $HARNESS_ROOT/templates/ and $HARNESS_ROOT/adapters/ — never from
# $HARNESS_ROOT/wiki/ (this repo's own dogfood docs). The broader
# smoke-install-bash.sh covers adapter/command placement; this script
# is narrow and targets the wiki-boundary rule specifically.
#
# Usage (from repo root):
#   bash scripts/test-install.sh
#
# Checks:
#   (a) install.sh runs cleanly into a scratch dir.
#   (b) scratch/wiki/ matches templates/wiki/ BYTE-FOR-BYTE (diff -r).
#   (c) No content from $HARNESS_ROOT/wiki/ appears in scratch/wiki/
#       (hash-based; catches renames and content leaks the diff misses).
#   (d) .github/workflows/wiki-sync.yml is present in the scratch install.
#
# Exit codes:
#   0 = installer boundary intact.
#   non-zero = boundary breached or install.sh is broken.

set -euo pipefail

HARNESS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

echo "==> install into $SCRATCH"
bash "$HARNESS_ROOT/install.sh" "$SCRATCH" > "$SCRATCH/.install.log"

# ── (b) scratch/wiki/ == templates/wiki/ byte-for-byte ──────────────────────
echo "==> [b] scratch/wiki/ byte-for-byte == templates/wiki/"
if ! diff -r "$HARNESS_ROOT/templates/wiki/" "$SCRATCH/wiki/" > "$SCRATCH/.diff.log" 2>&1; then
  echo "FAIL: scratch/wiki/ differs from templates/wiki/" >&2
  sed 's/^/    /' "$SCRATCH/.diff.log" >&2
  exit 1
fi
echo "    diff -r clean"

# ── (c) no content from $HARNESS_ROOT/wiki/ leaked into scratch/wiki/ ───────
echo "==> [c] no HARNESS_ROOT/wiki/ content leaked into scratch/wiki/"
python3 - "$HARNESS_ROOT" "$SCRATCH" <<'PY' || exit 1
import hashlib, os, sys
harness, scratch = sys.argv[1], sys.argv[2]

def hashes(root):
    out = {}
    if not os.path.isdir(root):
        return out
    for dp, _, fns in os.walk(root):
        for fn in fns:
            full = os.path.join(dp, fn)
            h = hashlib.sha256(open(full, 'rb').read()).hexdigest()
            out.setdefault(h, []).append(os.path.relpath(full, root))
    return out

h_harness   = hashes(os.path.join(harness, 'wiki'))
h_templates = hashes(os.path.join(harness, 'templates', 'wiki'))
h_scratch   = hashes(os.path.join(scratch, 'wiki'))

# A leak = a hash present in $HARNESS_ROOT/wiki/ AND scratch/wiki/, but NOT
# also in templates/wiki/. (If a file happens to be identical in both
# templates/wiki/ and the dogfood wiki/, that's not a leak — scratch got it
# from templates/.)
leak = (set(h_harness) & set(h_scratch)) - set(h_templates)
if leak:
    print('FAIL: $HARNESS_ROOT/wiki/ content appears in scratch/wiki/:')
    for sha in leak:
        print(f'  sha={sha[:12]} wiki={h_harness[sha]} scratch={h_scratch[sha]}')
    sys.exit(1)
print(f'    hashes clean ({len(h_harness)} wiki files checked against {len(h_scratch)} scratch files)')
PY

# ── (d) wiki-sync workflow reached the scratch install ──────────────────────
echo "==> [d] .github/workflows/wiki-sync.yml present"
if [[ ! -f "$SCRATCH/.github/workflows/wiki-sync.yml" ]]; then
  echo "FAIL: .github/workflows/wiki-sync.yml missing from scratch install" >&2
  exit 1
fi
echo "    present"

echo "==> test-install: OK"
