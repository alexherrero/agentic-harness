# evidence-tracker — default-FAIL evidence enforcement for /work.
# Mirrors evidence-tracker.sh for Windows / pwsh hosts.
#
# Fires on Claude Code's PreToolUse event (matcher Read|Write|Edit). Reads
# the PreToolUse JSON event from stdin and shells out to evidence_tracker.py
# which decides allow (exit 0) or block (exit 2).
#
# Graceful-skip: never blocks tool calls when Python isn't available or the
# evidence_tracker.py helper isn't installed.
#
# See hook.md in this directory for full documentation.

# NOTE: do NOT set ErrorActionPreference='Stop' — graceful-skip pattern;
# hook must never crash the session.
$ErrorActionPreference = 'Continue'

$helper = '.claude/hooks/evidence_tracker.py'

if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
    # Helper not installed — silently pass through.
    exit 0
}

# Resolve Python: try python3 first, fall back to python.
$python = $null
foreach ($cmd in @('python3', 'python')) {
    $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($resolved) { $python = $resolved.Source; break }
}

if (-not $python) {
    # Python not available — silently pass through.
    exit 0
}

# Forward stdin (PreToolUse event JSON) to the Python helper and propagate
# its exit code. PowerShell pipes stdin from the parent process through.
& $python $helper --mode check
exit $LASTEXITCODE
