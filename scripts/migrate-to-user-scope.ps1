<#
.SYNOPSIS
    V4 #30 plan 3 per-project → user-scope migration (pwsh twin).

.DESCRIPTION
    Walks a target project's <target>/.claude/{skills,hooks,agents,commands}/
    tree, classifies each entry via SHA256 compare against the agentm +
    crickets source clones, then (with -Apply) moves byte-identical content
    out of the per-project install so the user-scope install at ~/.claude/
    becomes the single source of truth. Idempotent + reversible via
    -Rollback.

.PARAMETER Target
    Project path (default: $PWD).

.PARAMETER Apply
    Execute the migration (default is preview).

.PARAMETER Rollback
    Reverse a prior migration via .agentm-migrate-record.json.

.PARAMETER Cleanup
    Opt-in destructive removal of empty .claude/{...}/ install subdirs
    after byte-identical verification.

.PARAMETER Force
    Migrate operator-edited files anyway (with backup). Only applies with
    -Apply.

.PARAMETER NoRegister
    Skip auto-registering the repo in repo_registry. Default: auto-register
    on successful -Apply.

.PARAMETER RegistrySlug
    Slug to use when auto-registering. Default: inferred from
    <target>/.harness/project.json or basename.

.PARAMETER AgentmPath
    Override agentm source clone path.

.PARAMETER CricketsPath
    Override crickets source clone path.

.PARAMETER Yes
    Skip interactive confirms (CI / scripted use).

.PARAMETER CiOverride
    Allow run when $env:CI=true detected (default refuses).

.NOTES
    State matrix (per plan #24 task 5):
      (1) No <target>/.claude/ at all                → graceful no-op exit 0.
      (2) .claude/ with content + no install-state   → pre-V4.3; primary migrate path.
      (3) .claude/ + install-state mode=project      → V4.3+ explicit per-project;
                                                       requires -Yes confirmation.
      (4) install-state mode=user OR no .claude/     → already user-scope; exit 0.

    Per V4 #30 plan 3 of 3 task 4 + 5. Pattern mirrors V4 #26
    migrate-harness-to-vault.ps1.
#>
[CmdletBinding()]
param(
    [string]$Target = $PWD,
    [switch]$Apply,
    [switch]$Rollback,
    [switch]$Cleanup,
    [switch]$Force,
    [switch]$NoRegister,
    [string]$RegistrySlug = "",
    [string]$AgentmPath = "",
    [string]$CricketsPath = "",
    [switch]$Yes,
    [switch]$CiOverride
)

# ── argument sanity ──────────────────────────────────────────────────────
$modesSet = 0
if ($Apply) { $modesSet++ }
if ($Rollback) { $modesSet++ }
if ($Cleanup) { $modesSet++ }
if ($modesSet -gt 1) {
    Write-Error "-Apply / -Rollback / -Cleanup are mutually exclusive."
    exit 2
}

# ── resolve target ───────────────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
    Write-Error "Target is not a directory: $Target"
    exit 1
}
$Target = (Resolve-Path -LiteralPath $Target).Path

# ── CI guard ─────────────────────────────────────────────────────────────
if (($env:CI -eq "true") -and (-not $CiOverride)) {
    Write-Error @"
Refusing to run inside CI (`$env:CI=true detected).
  CI runners typically use per-project installs by design.
  Re-run with -CiOverride if you really intend to migrate inside CI.
"@
    exit 4
}

# ── locate helpers ───────────────────────────────────────────────────────
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $Here "..")).Path
$LibPy = Join-Path $RepoRoot "lib/install/python"
$InstallMigratePy = Join-Path $LibPy "install_migrate.py"
$InstallStatePy = Join-Path $LibPy "install_state.py"
$RepoRegistryPy = Join-Path $RepoRoot "scripts/repo_registry.py"
$InstallSh = Join-Path $RepoRoot "install.sh"

foreach ($f in @($InstallMigratePy, $InstallStatePy, $RepoRegistryPy)) {
    if (-not (Test-Path -LiteralPath $f)) {
        Write-Error "Required helper not found: $f`n  (Did you run this from a checked-out agentm clone?)"
        exit 1
    }
}

# ── 4-state detection ────────────────────────────────────────────────────
# v4.5.1: prefer .agentm-config.json; fall back to legacy .agentm-install-state.json.
$ClaudeDir = Join-Path $Target ".claude"
$InstallStateJson = Join-Path $ClaudeDir ".agentm-config.json"
$LegacyStateJson = Join-Path $ClaudeDir ".agentm-install-state.json"
if (-not (Test-Path -LiteralPath $InstallStateJson) -and (Test-Path -LiteralPath $LegacyStateJson)) {
    $InstallStateJson = $LegacyStateJson
}
$HasClaudeContent = $false
if (Test-Path -LiteralPath $ClaudeDir -PathType Container) {
    foreach ($sub in @("skills", "hooks", "agents", "commands")) {
        $subPath = Join-Path $ClaudeDir $sub
        if (Test-Path -LiteralPath $subPath -PathType Container) {
            $children = Get-ChildItem -LiteralPath $subPath -Force -ErrorAction SilentlyContinue
            if ($children -and $children.Count -gt 0) {
                $HasClaudeContent = $true
                break
            }
        }
    }
}
$InstallStateMode = ""
if (Test-Path -LiteralPath $InstallStateJson) {
    try {
        $isData = Get-Content -LiteralPath $InstallStateJson -Raw | ConvertFrom-Json
        $InstallStateMode = "$($isData.mode)"
    } catch {
        $InstallStateMode = ""
    }
}

$state = "unknown"
if (-not $HasClaudeContent) {
    $state = "no-claude"
} elseif (-not $InstallStateMode) {
    $state = "pre-v4.3"
} elseif ($InstallStateMode -eq "project") {
    $state = "explicit-project"
} elseif ($InstallStateMode -eq "user") {
    $state = "already-user"
} else {
    $state = "pre-v4.3"
}

# ── handle "nothing to do" states up front ───────────────────────────────
# Exception: -Rollback runs the rollback flow regardless; -Cleanup also runs
# regardless because its purpose is to remove the now-empty install subdirs.
if (($state -eq "no-claude") -and (-not $Rollback) -and (-not $Cleanup)) {
    Write-Host "No per-project install detected at $Target/.claude/."
    Write-Host "If you want a user-scope install, run:"
    Write-Host "    bash $InstallSh --scope user $Target"
    exit 0
}
if (($state -eq "already-user") -and (-not $Rollback) -and (-not $Cleanup)) {
    Write-Host "Already user-scope (mode=user in $InstallStateJson). Nothing to migrate."
    exit 0
}

# ── banner ───────────────────────────────────────────────────────────────
if ((-not $Apply) -and (-not $Rollback) -and (-not $Cleanup)) {
    Write-Host "==> [PREVIEW MODE - no changes will be made]"
}
Write-Host "==> migrate-to-user-scope"
Write-Host "    target:       $Target"
Write-Host "    state:        $state"
if ($Rollback) { Write-Host "    mode:         rollback" }
elseif ($Cleanup) { Write-Host "    mode:         cleanup" }
elseif ($Apply) { Write-Host "    mode:         apply" }
else { Write-Host "    mode:         preview (default)" }
Write-Host ""

# ── DC-10 confirmation for explicit-project state ────────────────────────
if (($state -eq "explicit-project") -and $Apply -and (-not $Yes)) {
    Write-Host "Target's install-state.json explicitly sets mode=project."
    Write-Host "Migration may be unwanted - see wiki/how-to/Use-Per-Project-Install.md"
    Write-Host "for cases where --scope project is the right choice."
    $yn = Read-Host "Proceed with migration anyway? [y/N]"
    if ($yn -notmatch '^[Yy]') {
        Write-Host "Aborted."
        exit 0
    }
}

# ── shared Python invocation helper ──────────────────────────────────────
function Invoke-Migrate {
    param([string]$Mode, [string[]]$Extra = @())
    $args = @("--mode", $Mode)
    if ($AgentmPath) { $args += @("--agentm", $AgentmPath) }
    if ($CricketsPath) { $args += @("--crickets", $CricketsPath) }
    if ($RegistrySlug) { $args += @("--registry-slug", $RegistrySlug) }
    if ($Force) { $args += @("--force") }
    $args += $Extra
    $args += $Target
    & python3 $InstallMigratePy @args
}

# ── handle -Rollback ─────────────────────────────────────────────────────
if ($Rollback) {
    Write-Host "==> rolling back migration via .agentm-migrate-record.json"
    $jsonOut = Invoke-Migrate -Mode "rollback" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error ($jsonOut -join "`n")
        exit 3
    }
    $rollData = $jsonOut | ConvertFrom-Json
    Write-Host ($jsonOut -join "`n")
    Write-Host ""
    $restoredCount = if ($rollData.restored) { $rollData.restored.Count } else { 0 }
    $skippedCount = if ($rollData.skipped) { $rollData.skipped.Count } else { 0 }
    Write-Host "==> rollback complete: $restoredCount restored, $skippedCount skipped"
    if (-not $NoRegister) {
        $slug = $RegistrySlug
        if (-not $slug) { $slug = Split-Path -Leaf $Target }
        Write-Host "==> unregistering '$slug' from repo_registry (best-effort)"
        & python3 $RepoRegistryPy unregister $slug 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  (slug not registered or registry unavailable; ignored)"
        }
    }
    exit 0
}

# ── handle -Cleanup ──────────────────────────────────────────────────────
if ($Cleanup) {
    Write-Host "==> cleanup: verifying + removing empty install subdirs"
    $jsonOut = Invoke-Migrate -Mode "cleanup" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error ($jsonOut -join "`n")
        exit 3
    }
    $cleanData = $jsonOut | ConvertFrom-Json
    Write-Host ($jsonOut -join "`n")
    if ($cleanData.refused) {
        Write-Host ""
        Write-Host "==> cleanup REFUSED - operator content remains under .claude/{...}/."
        Write-Host "    Either move/remove that content, or accept the un-cleaned state."
        exit 5
    }
    Write-Host ""
    Write-Host "==> cleanup complete."
    exit 0
}

# ── preview OR apply ─────────────────────────────────────────────────────
$jsonOut = Invoke-Migrate -Mode "classify" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error ($jsonOut -join "`n")
    Write-Host ""
    Write-Host "Hint: source clones may be missing or path overrides may be wrong."
    Write-Host "Detected source clones:"
    & python3 $InstallStatePy detect 2>&1
    exit 1
}

try {
    $classifyData = ($jsonOut -join "`n") | ConvertFrom-Json
    $classified = $classifyData.classified
} catch {
    $classified = @()
}

if ((-not $classified) -or ($classified.Count -eq 0)) {
    Write-Host "No per-project install entries to classify (empty .claude/)."
} else {
    Write-Host ("  {0,-22} {1,-10} {2}" -f "CLASSIFICATION", "CLONE", "PATH")
    Write-Host ("  {0,-22} {1,-10} {2}" -f ("-" * 22), ("-" * 10), ("-" * 40))
    $counts = @{}
    foreach ($e in $classified) {
        $cls = $e.classification
        if (-not $counts.ContainsKey($cls)) { $counts[$cls] = 0 }
        $counts[$cls]++
        $clone = if ($e.source_clone) { $e.source_clone } else { "-" }
        Write-Host ("  {0,-22} {1,-10} {2}" -f $cls, $clone, $e.rel_path)
    }
    Write-Host ""
    Write-Host "Summary:"
    foreach ($k in ($counts.Keys | Sort-Object)) {
        Write-Host ("  {0,-22} {1}" -f $k, $counts[$k])
    }
}

if (-not $Apply) {
    Write-Host ""
    Write-Host "Preview only. Re-run with -Apply to execute the migration."
    exit 0
}

# ── apply ────────────────────────────────────────────────────────────────
if (-not $Yes) {
    Write-Host ""
    $yn = Read-Host "Apply this migration? [y/N]"
    if ($yn -notmatch '^[Yy]') {
        Write-Host "Aborted."
        exit 0
    }
}

# Infer registry slug if not explicit
$slug = $RegistrySlug
if (-not $slug) {
    $projectJson = Join-Path $Target ".harness/project.json"
    if (Test-Path -LiteralPath $projectJson) {
        try {
            $pj = Get-Content -LiteralPath $projectJson -Raw | ConvertFrom-Json
            $slug = "$($pj.vault_project)"
            if (-not $slug) { $slug = "$($pj.slug)" }
        } catch { $slug = "" }
    }
    if (-not $slug) { $slug = Split-Path -Leaf $Target }
}

Write-Host "==> applying migration (slug=$slug)"
$jsonOut = Invoke-Migrate -Mode "apply" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error ($jsonOut -join "`n")
    exit 3
}
Write-Host ($jsonOut -join "`n")
try {
    $applyData = ($jsonOut -join "`n") | ConvertFrom-Json
    $skippedForce = if ($applyData.skipped_force_needed) { $applyData.skipped_force_needed } else { 0 }
} catch {
    $skippedForce = 0
}

# Populate ~/.claude/ via install.sh --scope user (idempotent)
if (Test-Path -LiteralPath $InstallSh) {
    Write-Host ""
    Write-Host "==> ensuring ~/.claude/ is populated via 'bash install.sh --scope user'"
    & bash $InstallSh --scope user *> $null
    # Best-effort; exit code intentionally ignored.
}

# Auto-register unless opted out
if (-not $NoRegister) {
    Write-Host ""
    Write-Host "==> auto-registering '$slug' in repo_registry (root=$Target)"
    & python3 $RepoRegistryPy register $slug --root $Target 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  registered."
    } else {
        Write-Host "  (registration skipped - vault unavailable or already registered)"
    }
}

Write-Host ""
Write-Host "==> apply complete."
if ($skippedForce -gt 0) {
    Write-Host "    $skippedForce operator-edited file(s) skipped - re-run with -Force to migrate."
}
Write-Host "    Run with -Cleanup once verified to remove .claude/{...}/ install subdirs."
Write-Host "    Run with -Rollback to reverse this migration."
exit 0
