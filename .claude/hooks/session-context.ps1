# VECTOR SessionStart hook: report repository state as session context.
# Read-only: runs only `git branch --show-current`, `git rev-parse --short HEAD`, and
# `git status --short` (with --no-optional-locks so the index is never rewritten).
# Plain stdout from a SessionStart hook is added to Claude's context.
# Keep ASCII-only: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.

$ErrorActionPreference = 'Continue'

$dir = $env:CLAUDE_PROJECT_DIR
if ([string]::IsNullOrWhiteSpace($dir)) {
    $dir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}

function Invoke-GitRead {
    param([string[]]$GitArgs)
    $out = & git --no-optional-locks -C $dir @GitArgs 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return $out
}

$branch = Invoke-GitRead @('branch', '--show-current')
$head   = Invoke-GitRead @('rev-parse', '--short', 'HEAD')
$status = Invoke-GitRead @('status', '--short')

Write-Output 'VECTOR SESSION CONTEXT'
if ($null -eq $head) {
    Write-Output 'git state: UNAVAILABLE (not a git repository, or git not on PATH)'
} else {
    if ([string]::IsNullOrWhiteSpace($branch)) { $branch = '(detached HEAD)' }
    Write-Output ('branch: ' + $branch)
    Write-Output ('HEAD: ' + $head)
    $lines = @($status | Where-Object { $_ })
    if ($lines.Count -eq 0) {
        Write-Output 'working tree: CLEAN'
    } else {
        Write-Output ('working tree: DIRTY (' + $lines.Count + ' entries)')
        $lines | Select-Object -First 40 | ForEach-Object { Write-Output ('  ' + $_) }
        if ($lines.Count -gt 40) { Write-Output ('  ... and ' + ($lines.Count - 40) + ' more') }
    }
}
Write-Output 'Reminders:'
Write-Output '- Read PRODUCT.md and STATUS.md before production changes.'
Write-Output '- Never discard an existing dirty working tree.'
