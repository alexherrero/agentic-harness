# memory-recall-prompt-submit — inject query-relevant MemoryVault entries on prompt submit (Windows / pwsh).
# Mirrors memory-recall-prompt-submit.sh.
#
# See hook.md in this directory for full documentation.

# NOTE: no `$ErrorActionPreference = 'Stop'` — graceful-skip pattern; hook must
# never block the user prompt. Errors are caught + swallowed inline.

$RecallPy = ".claude/skills/memory/scripts/recall.py"
if (-not (Test-Path $RecallPy)) {
    # Memory skill not installed; nothing to do.
    exit 0
}

if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    exit 0
}

$Py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

# Pipe stdin through. PowerShell's process redirection forwards stdin
# automatically when using the call operator without -RedirectStandardInput.
# Use $Input to forward stdin from the script's calling pipeline if any.
$Input | & $Py $RecallPy prompt-submit
exit $LASTEXITCODE
