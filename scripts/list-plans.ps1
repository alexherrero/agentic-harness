# list-plans.ps1 — Windows twin of the cross-repo plan-listing tool.
#
# Walks <vault>/projects/*/_harness/PLAN.md, parses title + Status + mtime,
# prints a one-row-per-project summary table. Resolves legacy
# personal-projects/ if vault rename hasn't run yet.
#
# Usage:
#   pwsh -NoProfile -File list-plans.ps1 [-VaultPath <path>] [-All] [-Help]

[CmdletBinding()]
param(
    [string]$VaultPath = $env:MEMORY_VAULT_PATH,
    [switch]$All,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

if ($Help) {
    Get-Content $PSCommandPath | Where-Object { $_ -match '^#' -or $_ -eq '' } | ForEach-Object { $_ -replace '^# ?', '' }
    exit 0
}

if (-not $VaultPath) {
    Write-Error 'vault path not provided. Set MEMORY_VAULT_PATH or pass -VaultPath.'
    exit 1
}
if (-not (Test-Path -LiteralPath $VaultPath -PathType Container)) {
    Write-Error "vault path is not a directory: $VaultPath"
    exit 1
}
$VaultPath = (Resolve-Path -LiteralPath $VaultPath).ProviderPath

$projectsNew = Join-Path $VaultPath 'projects'
$projectsLegacy = Join-Path $VaultPath 'personal-projects'
if (Test-Path -LiteralPath $projectsNew -PathType Container) {
    $ProjectsDir = $projectsNew
} elseif (Test-Path -LiteralPath $projectsLegacy -PathType Container) {
    $ProjectsDir = $projectsLegacy
} else {
    Write-Error "no projects/ or personal-projects/ dir found under $VaultPath"
    exit 1
}

$rows = @()
foreach ($projectDir in (Get-ChildItem -LiteralPath $ProjectsDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name)) {
    $slug = $projectDir.Name
    $plan = Join-Path $projectDir.FullName '_harness/PLAN.md'
    if (-not (Test-Path -LiteralPath $plan -PathType Leaf)) {
        $rows += [pscustomobject]@{ slug = $slug; title = '(no in-flight plan)'; status = '-'; updated = '-' }
        continue
    }
    try {
        $text = Get-Content -LiteralPath $plan -Raw -Encoding utf8
    } catch {
        $rows += [pscustomobject]@{ slug = $slug; title = '(unreadable)'; status = '?'; updated = '?' }
        continue
    }
    $title = '(no title)'
    foreach ($line in ($text -split "`n" | Select-Object -First 10)) {
        if ($line -match '^# Plan:\s*(.+)$') {
            $title = $Matches[1].Trim()
            break
        }
    }
    $status = '?'
    foreach ($line in ($text -split "`n" | Select-Object -First 30)) {
        if ($line -match '^\*\*Status:\*\*\s*(\S+)') {
            $status = $Matches[1].ToLower()
            break
        }
    }
    $updated = (Get-Item -LiteralPath $plan).LastWriteTime.ToString('yyyy-MM-dd')
    $rows += [pscustomobject]@{ slug = $slug; title = $title; status = $status; updated = $updated }
}

if (-not $All) {
    $rows = $rows | Where-Object { $_.status -in @('planning', 'in-progress', '?', '-') }
}

if (-not $rows -or @($rows).Count -eq 0) {
    Write-Host '(no in-flight plans across vault projects)'
    exit 0
}

$rows | Format-Table -AutoSize
