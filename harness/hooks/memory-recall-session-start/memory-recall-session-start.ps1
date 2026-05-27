# memory-recall-session-start — load MemoryVault always-load entries on session boot (Windows / pwsh).
# Mirrors memory-recall-session-start.sh.
#
# See hook.md in this directory for full documentation.

# NOTE: no `$ErrorActionPreference = 'Stop'` — graceful-skip pattern; hook must
# never block session boot. Errors are caught + swallowed inline.

# Require python3 — exit 0 if missing.
if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    exit 0
}
$Py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

# ── Crash-recovery marker (plan #7a part 3 task 6) ─────────────────────────
# Parse SessionStart event's stdin JSON for session_id + cwd; write a
# .harness/session-id-<sid>.start marker so the idle hook's orphan-recovery
# sweep can detect crashed sessions. Marker write is best-effort.
$Payload = ($Input | Out-String).Trim()
if ($Payload) {
    $ParseDriver = @"
import json, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
sid = d.get('session_id') or ''
cwd = d.get('cwd') or ''
if sid:
    print(f'{sid}\t{cwd}')
"@
    $Parsed = ($Payload | & $Py -c $ParseDriver 2>$null).Trim()
    if ($Parsed) {
        $Parts = $Parsed -split "`t"
        $SessionId = $Parts[0]
        $Cwd = if ($Parts.Length -gt 1 -and $Parts[1]) { $Parts[1] } else { (Get-Location).Path }
        # Transcript path slug (same formula as memory-reflect-stop.ps1; strip ':' for Windows).
        $CwdSlug = "-" + (($Cwd -replace '[\\/]', '-') -replace ':', '')
        $TranscriptPath = Join-Path $HOME ".claude/projects/$CwdSlug/$SessionId.jsonl"
        # Ensure .harness/ exists.
        $HarnessDir = ".harness"
        if (-not (Test-Path $HarnessDir)) {
            New-Item -ItemType Directory -Path $HarnessDir -Force -ErrorAction SilentlyContinue | Out-Null
        }
        $Marker = Join-Path $HarnessDir "session-id-$SessionId.start"
        if (-not (Test-Path $Marker)) {
            $Now = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
            $MarkerContent = @"
session_id: $SessionId
started_at: $Now
transcript: $TranscriptPath
"@
            try {
                Set-Content -LiteralPath $Marker -Value $MarkerContent -ErrorAction SilentlyContinue
            } catch {}
        }
    }
}

# ── Recall pass ────────────────────────────────────────────────────────────
$RecallPy = ".claude/skills/memory/scripts/recall.py"
if (-not (Test-Path $RecallPy)) {
    exit 0
}

& $Py $RecallPy session-start
exit $LASTEXITCODE
