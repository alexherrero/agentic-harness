#!/usr/bin/env bash
# cross-review.sh — adversarial review via a different model (Gemini).
#
# The in-process adversarial-reviewer runs on the same model that wrote the
# code; same-model review is an echo chamber. This script shells out to the
# Gemini CLI for a cross-model second opinion.
#
# Usage:
#   cat review-material.txt | .harness/scripts/cross-review.sh
#
# The stdin "review material" is already-assembled text built by the caller
# (the adversarial-reviewer-cross sub-agent). It should include delimited
# sections: the diff, the PLAN task, and optionally AGENTS.md.
#
# Exit codes:
#   0 — review produced, output on stdout matches the contract
#   1 — gemini not installed / not authed — caller should fall back
#   2 — gemini ran but violated the output contract twice — caller decides
#
# The contract (what stdout must match): exactly one of
#   1. A failing test inside a fenced code block
#   2. A line starting with `DEFECT: path:line`
#   3. A block starting with `NO ISSUES FOUND`
# Prose-only responses are rejected.

set -uo pipefail

MODEL="gemini-3.1-pro-preview"

command -v gemini >/dev/null 2>&1 || {
  echo "cross-review: gemini CLI not found — caller should fall back" >&2
  exit 1
}

material=$(cat)
if [[ -z "$material" ]]; then
  echo "cross-review: no review material on stdin" >&2
  exit 2
fi

# Use `read -r -d ''` for the heredoc assignment — `$(cat <<'EOF'...)` gets
# confused by backticks inside fenced code blocks in the prompt body.
IFS='' read -r -d '' framing <<'FRAMING_EOF' || true
You are an adversarial code reviewer. The code below likely contains bugs — your job is to find them. A review that returns "looks good" is either correct (rare) or a failure of rigor (common). Default to skepticism.

You MUST produce exactly ONE of these three forms as your entire response. No prose preamble, no prose afterword.

FORM 1 — failing test (preferred):
Start with a triple-backtick fenced code block whose first line is a path comment (// or #). Put executable test code that fails against the current implementation inside the fence.

FORM 2 — specific defect reference:
DEFECT: <path/file>:<line>
Spec says: <quote or paraphrase from the PLAN task>
Actual: <what the code does>
Minimal reproducer: <input> → <actual> ≠ <expected>

FORM 3 — explicit no-issues finding (use ONLY if you genuinely found nothing after checking all categories below):
NO ISSUES FOUND
Reviewed: <file list>
Categories checked: spec adherence, edge cases, API design, security concerns without a lint rule, dead code, regressions

Categories to check:
- Spec adherence vs. the PLAN task's Verification clause
- Edge cases not covered by existing tests (empty input, boundary values, concurrent access, error paths)
- API design — public interfaces, naming, error types
- Security concerns not caught by lints
- Dead code or half-finished branches
- Regressions in code unchanged by the diff

Prose-only critiques like "consider adding error handling" or "this could be cleaner" are NOT acceptable output. If you cannot produce one of the three forms, produce NO ISSUES FOUND — but only if you honestly checked every category.
FRAMING_EOF

# Contract validation: pattern-match the first non-whitespace content.
validate() {
  local out="$1"
  # Strip leading whitespace and any markdown fence decoration, then check
  # the first few lines for one of the three markers.
  local head
  head=$(echo "$out" | sed -n '1,30p')
  if echo "$head" | grep -qE '^[[:space:]]*NO ISSUES FOUND'; then return 0; fi
  if echo "$head" | grep -qE '^[[:space:]]*DEFECT:[[:space:]]+\S+:[0-9]+'; then return 0; fi
  # Failing-test form: a fenced code block starting with `//` or `#` path comment
  if echo "$head" | grep -qE '^[[:space:]]*```'; then
    if echo "$head" | grep -qE '^[[:space:]]*(//|#)\s*\S+'; then return 0; fi
  fi
  return 1
}

call_gemini() {
  local prompt="$1"
  # Pass the framing via -p (short), and the bulk of the material via stdin.
  # `gemini -p` appends stdin to the prompt, per `gemini --help`.
  printf '%s\n' "$material" | gemini -p "$prompt" -m "$MODEL" -o text 2>/dev/null
}

output=$(call_gemini "$framing")
rc=$?
if [[ $rc -ne 0 || -z "$output" ]]; then
  echo "cross-review: gemini call failed (exit $rc)" >&2
  exit 1
fi

if validate "$output"; then
  printf '%s\n' "$output"
  exit 0
fi

# Retry once with a sharper format nudge.
retry_nudge="Your previous response did not match the required output format. Respond again using EXACTLY ONE of the three forms (failing test, DEFECT:, or NO ISSUES FOUND). No prose preamble. No prose outside the form."
retry_framing="${framing}"$'\n\n'"${retry_nudge}"

output=$(call_gemini "$retry_framing")
rc=$?
if [[ $rc -ne 0 || -z "$output" ]]; then
  echo "cross-review: gemini retry failed (exit $rc)" >&2
  exit 1
fi

if validate "$output"; then
  printf '%s\n' "$output"
  exit 0
fi

echo "cross-review: contract violated after retry. Raw output follows on stderr." >&2
printf '%s\n' "$output" >&2
exit 2
