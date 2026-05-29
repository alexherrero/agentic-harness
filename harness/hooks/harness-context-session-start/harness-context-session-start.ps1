#!/usr/bin/env pwsh
# harness-context-session-start (pwsh twin) — inject the project's vault
# PLAN.md/progress.md paths into session context on SessionStart.
# Mirrors harness-context-session-start.sh. Never blocks session boot. V4 #39.

$ErrorActionPreference = 'SilentlyContinue'

function Write-Skip([string]$reason) {
    [Console]::Error.WriteLine("[harness-context] $reason — skipped")
    exit 0
}

$python = (Get-Command python3 -ErrorAction SilentlyContinue) ?? (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { Write-Skip "python unavailable" }
$py = $python.Source

# ── Read SessionStart event JSON from stdin; extract cwd (DC-6) ──
$payload = [Console]::In.ReadToEnd()
$eventCwd = ""
if ($payload) {
    try { $eventCwd = ([string](($payload | ConvertFrom-Json).cwd)) } catch { $eventCwd = "" }
}
if (-not $eventCwd) { $eventCwd = (Get-Location).Path }
if (-not (Test-Path -LiteralPath $eventCwd -PathType Container)) { Write-Skip "event cwd not a directory" }

# ── Resolve harness_memory.py: recorded agentm source clone → fallback ──
$resolver = ""
$cfg = Join-Path $HOME ".claude/.agentm-config.json"
if (Test-Path -LiteralPath $cfg) {
    try {
        $clone = [string]((Get-Content -Raw -LiteralPath $cfg | ConvertFrom-Json).source_clones.agentm)
        if ($clone) {
            $cand = Join-Path $clone "scripts/harness_memory.py"
            if (Test-Path -LiteralPath $cand) { $resolver = $cand }
        }
    } catch { }
}
if (-not $resolver) {
    $fallback = Join-Path $HOME "Antigravity/agentm/scripts/harness_memory.py"
    if (Test-Path -LiteralPath $fallback) { $resolver = $fallback }
}
if (-not $resolver) { Write-Skip "harness_memory.py resolver unavailable" }

function Resolve-State([string]$name) {
    try {
        Push-Location -LiteralPath $eventCwd
        # 500ms budget via a job; kill on overrun (degraded-graceful).
        $j = Start-Job { param($p,$r,$n) & $p $r vault-state-path $n 2>$null } -ArgumentList $py,$resolver,$name
        if (Wait-Job $j -Timeout 1 | Out-Null; $j.State -eq 'Completed') {
            return ([string](Receive-Job $j)).Trim()
        }
        Stop-Job $j -ErrorAction SilentlyContinue
        return ""
    } catch { return "" }
    finally { Pop-Location -ErrorAction SilentlyContinue; if ($j) { Remove-Job $j -Force -ErrorAction SilentlyContinue } }
}

$planPath = Resolve-State "PLAN.md"
$progressPath = Resolve-State "progress.md"

if ($planPath -and $progressPath -and (Test-Path -LiteralPath $planPath) -and (Test-Path -LiteralPath $progressPath)) {
    Write-Output "[agentm] Project state for this repo lives in the vault, not in .harness/:"
    Write-Output "  PLAN.md:     $planPath"
    Write-Output "  progress.md: $progressPath"
    Write-Output "Read PLAN.md before answering plan-status questions or running /work, /review, /release."
    $slug = Split-Path (Split-Path (Split-Path $planPath -Parent) -Parent) -Leaf
    [Console]::Error.WriteLine("[harness-context] injected vault paths for slug=$slug")
} else {
    [Console]::Error.WriteLine("[harness-context] non-harness cwd or vault paths unresolved — skipped")
}
exit 0
