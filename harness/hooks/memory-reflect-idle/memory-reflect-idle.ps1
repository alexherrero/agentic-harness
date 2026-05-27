# memory-reflect-idle — orphan-recovery + idle reflection sweep (Windows / pwsh).
# Mirrors memory-reflect-idle.sh.
#
# See hook.md in this directory for full documentation.

# NOTE: no `$ErrorActionPreference = 'Stop'` — graceful-skip pattern.

$ReflectPy = ".claude/skills/memory/scripts/reflect.py"
if (-not (Test-Path $ReflectPy)) {
    exit 0
}

if (-not (Get-Command python3 -ErrorAction SilentlyContinue) -and
    -not (Get-Command python -ErrorAction SilentlyContinue)) {
    exit 0
}

$Py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

# Thresholds (env overrides + defaults).
$IdleThresholdSec = if ($env:MEMORY_IDLE_THRESHOLD_SEC) { [int]$env:MEMORY_IDLE_THRESHOLD_SEC } else { 3600 }
$GcThresholdSec = if ($env:MEMORY_REFLECTED_GC_SEC) { [int]$env:MEMORY_REFLECTED_GC_SEC } else { 2592000 }

$HarnessDir = ".harness"
if (-not (Test-Path $HarnessDir)) {
    exit 0
}

$markers = @(Get-ChildItem -LiteralPath $HarnessDir -Filter 'session-id-*.start' -ErrorAction SilentlyContinue)
$reflectedMarkers = @(Get-ChildItem -LiteralPath $HarnessDir -Filter 'session-id-*.reflected' -ErrorAction SilentlyContinue)

# Note: removed an early `exit 0` here so the skill-discovery cadence-check
# (plan #7b task 3) still runs even when there's no orphan work to do.

$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$processedCount = 0

foreach ($marker in $markers) {
    $mtime = [DateTimeOffset]::new($marker.LastWriteTimeUtc).ToUnixTimeSeconds()
    $ageSec = $now - $mtime
    if ($ageSec -lt $IdleThresholdSec) {
        continue
    }

    # Parse transcript path from marker contents.
    $markerContents = Get-Content -LiteralPath $marker.FullName -ErrorAction SilentlyContinue
    $transcript = ($markerContents | Where-Object { $_ -match '^transcript:' } | Select-Object -First 1) -replace '^transcript:\s*', ''
    if (-not $transcript) {
        [Console]::Error.WriteLine("[memory-reflect-idle] marker $($marker.Name) missing 'transcript:' line (skipping)")
        continue
    }
    if (-not (Test-Path -LiteralPath $transcript)) {
        [Console]::Error.WriteLine("[memory-reflect-idle] marker $($marker.Name) transcript not found: $transcript (skipping)")
        continue
    }

    # Run reflection with --route (HIGH → canonical / MEDIUM+LOW → _inbox/).
    & $Py $ReflectPy $transcript "--summary" "--route" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $reflectedPath = $marker.FullName -replace '\.start$', '.reflected'
        try {
            Move-Item -LiteralPath $marker.FullName -Destination $reflectedPath -Force -ErrorAction Stop
            $processedCount++
        } catch {
            # Rename failed; marker stays for next pass.
        }
    }
}

# GC pass.
$gcCount = 0
foreach ($reflected in $reflectedMarkers) {
    $mtime = [DateTimeOffset]::new($reflected.LastWriteTimeUtc).ToUnixTimeSeconds()
    $ageSec = $now - $mtime
    if ($ageSec -gt $GcThresholdSec) {
        try {
            Remove-Item -LiteralPath $reflected.FullName -Force -ErrorAction Stop
            $gcCount++
        } catch {}
    }
}

if ($markers.Count -gt 0 -or $gcCount -gt 0) {
    [Console]::Error.WriteLine("[memory-reflect-idle] Scanned $($markers.Count) .start + $($reflectedMarkers.Count) .reflected markers; processed $processedCount orphans, GC'd $gcCount old markers (idle threshold: ${IdleThresholdSec}s)")
}

# ── Skill-discovery cadence-checked scan (plan #7b task 3) ─────────────────
# Fire discover_skills.py with --cadence-check (self-throttles to configured
# cadence, default 7d). Graceful-skip if MEMORY_VAULT_PATH unset / script
# absent. Output → stderr so the hook's stdout stays clean.
$DiscoverPy = ".claude/skills/memory/scripts/discover_skills.py"
$VaultEnv = $env:MEMORY_VAULT_PATH
if ((Test-Path $DiscoverPy) -and $VaultEnv) {
    try {
        & $Py $DiscoverPy "--vault-path" $VaultEnv "--cadence-check" 2>&1 | ForEach-Object { [Console]::Error.WriteLine($_) }
    } catch {
        # Non-fatal — the hook never blocks on discover-skills failure.
    }
}

exit 0
