# cross-review.ps1 — adversarial review via a different model (Gemini).
# PowerShell twin of cross-review.sh.
#
# The in-process adversarial-reviewer runs on the same model that wrote the
# code; same-model review is an echo chamber. This script shells out to the
# Gemini CLI for a cross-model second opinion.
#
# Usage:
#   Get-Content review-material.txt | pwsh -File .harness/scripts/cross-review.ps1
#
# The stdin "review material" is already-assembled text built by the caller
# (the adversarial-reviewer-cross sub-agent). It should include delimited
# sections: the diff, the PLAN task, and optionally AGENTS.md.
#
# Exit codes:
#   0 — review produced, output on stdout matches the contract
#   1 — gemini not installed / not authed — caller should fall back
#   2 — gemini ran but violated the output contract twice — caller decides

$ErrorActionPreference = 'Continue'

$Model = 'gemini-3.1-pro-preview'

if (-not (Get-Command gemini -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine('cross-review: gemini CLI not found — caller should fall back')
    exit 1
}

$material = [Console]::In.ReadToEnd()
if (-not $material) {
    [Console]::Error.WriteLine('cross-review: no review material on stdin')
    exit 2
}

$framing = @'
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
'@

function Test-Contract([string]$out) {
    if (-not $out) { return $false }
    $head = ($out -split "`n" | Select-Object -First 30) -join "`n"
    if ($head -match '(?m)^\s*NO ISSUES FOUND') { return $true }
    if ($head -match '(?m)^\s*DEFECT:\s+\S+:\d+') { return $true }
    if ($head -match '(?ms)^\s*```[^\n]*\n\s*(//|#)\s*\S+') { return $true }
    return $false
}

function Invoke-Gemini([string]$prompt) {
    $material | & gemini -p $prompt -m $Model -o text 2>$null
}

$output = Invoke-Gemini $framing
$rc = $LASTEXITCODE
if ($rc -ne 0 -or -not $output) {
    [Console]::Error.WriteLine("cross-review: gemini call failed (exit $rc)")
    exit 1
}

if (Test-Contract $output) {
    $output
    exit 0
}

$retryNudge = "Your previous response did not match the required output format. Respond again using EXACTLY ONE of the three forms (failing test, DEFECT:, or NO ISSUES FOUND). No prose preamble. No prose outside the form."
$retryFraming = "$framing`n`n$retryNudge"

$output = Invoke-Gemini $retryFraming
$rc = $LASTEXITCODE
if ($rc -ne 0 -or -not $output) {
    [Console]::Error.WriteLine("cross-review: gemini retry failed (exit $rc)")
    exit 1
}

if (Test-Contract $output) {
    $output
    exit 0
}

[Console]::Error.WriteLine('cross-review: contract violated after retry. Raw output follows on stderr.')
[Console]::Error.WriteLine($output)
exit 2
