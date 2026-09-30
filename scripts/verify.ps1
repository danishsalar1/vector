#!/usr/bin/env pwsh
<#
.SYNOPSIS
    VECTOR verification script. Run before every commit.

.DESCRIPTION
    Runs all quality checks for the VECTOR project.
    If any required check fails, this script exits non-zero and you must NOT commit.

.USAGE
    .\scripts\verify.ps1
    .\scripts\verify.ps1 -SkipFrontend
    .\scripts\verify.ps1 -SkipPython
#>

param(
    [switch]$SkipFrontend,
    [switch]$SkipPython,
    [switch]$Quick  # Skip slow checks (build, full test coverage)
)

$ErrorActionPreference = "Stop"
$script:failures = @()
$script:passed = @()

function Write-Header($text) {
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
}

function Write-Step($text) {
    Write-Host ""
    Write-Host "-- $text" -ForegroundColor Yellow
}

function Record-Result($name, $success, $output = "") {
    if ($success) {
        Write-Host "  [PASS] $name" -ForegroundColor Green
        $script:passed += $name
    } else {
        Write-Host "  [FAIL] $name" -ForegroundColor Red
        if ($output) { Write-Host $output -ForegroundColor DarkRed }
        $script:failures += $name
    }
}

function Run-Check($name, $scriptBlock) {
    Write-Step $name
    $prevEAP = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $global:LASTEXITCODE = 0
        $output = & $scriptBlock 2>&1
        $exitCode = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        if ($null -ne $exitCode -and $exitCode -ne 0) {
            Record-Result $name $false ($output | Out-String)
        } else {
            Record-Result $name $true
        }
    } catch {
        $ErrorActionPreference = $prevEAP
        Record-Result $name $false $_.Exception.Message
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Header "VECTOR Verification Script"
Write-Host "Repository: $repoRoot"
Write-Host "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# ============================================================
# Python: Local Agent
# ============================================================
if (-not $SkipPython) {
    Write-Header "Python - Local Agent"
    $agentDir = Join-Path $repoRoot "local-agent"

    # Check that uv or pip is available
    $uvAvailable = $null -ne (Get-Command uv -ErrorAction SilentlyContinue)

    if ($uvAvailable) {
        Run-Check "Agent: Install deps (uv)" {
            Set-Location $agentDir
            uv pip install -e '.[dev]' --system -q
        }
        Run-Check "Agent: Ruff lint" {
            Set-Location $agentDir
            uv run ruff check src/ tests/
        }
        Run-Check "Agent: Ruff format" {
            Set-Location $agentDir
            uv run ruff format --check src/ tests/
        }
        Run-Check "Agent: Mypy" {
            Set-Location $agentDir
            uv run mypy src/
        }
        Run-Check "Agent: Pytest" {
            Set-Location $agentDir
            uv run pytest tests/ -v --tb=short
        }
    } else {
        Write-Host "  [WARN] uv not found - trying pip install" -ForegroundColor Yellow
        Run-Check "Agent: pip install" {
            Set-Location $agentDir
            python -m pip install -e '.[dev]' --no-warn-script-location -q
        }
        Run-Check "Agent: Ruff lint" {
            Set-Location $agentDir
            python -m ruff check src/ tests/
        }
        Run-Check "Agent: Ruff format" {
            Set-Location $agentDir
            python -m ruff format --check src/ tests/
        }
        Run-Check "Agent: Mypy" {
            Set-Location $agentDir
            python -m mypy src/
        }
        Run-Check "Agent: Pytest" {
            Set-Location $agentDir
            python -m pytest tests/ -v --tb=short
        }
    }

    Write-Header "Python - Intelligence"
    $intelDir = Join-Path $repoRoot "intelligence"

    if ($uvAvailable) {
        Run-Check "Intelligence: Install deps" {
            Set-Location $intelDir
            uv pip install -e '.[dev]' --system -q
        }
        Run-Check "Intelligence: Ruff lint" {
            Set-Location $intelDir
            uv run ruff check src/ tests/
        }
        Run-Check "Intelligence: Ruff format" {
            Set-Location $intelDir
            uv run ruff format --check src/ tests/
        }
        Run-Check "Intelligence: Mypy" {
            Set-Location $intelDir
            uv run mypy src/
        }
        Run-Check "Intelligence: Pytest" {
            Set-Location $intelDir
            uv run pytest tests/ -v --tb=short
        }
    } else {
        Run-Check "Intelligence: Install deps" {
            Set-Location $intelDir
            python -m pip install -e '.[dev]' --no-warn-script-location -q
        }
        Run-Check "Intelligence: Ruff lint" {
            Set-Location $intelDir
            python -m ruff check src/ tests/
        }
        Run-Check "Intelligence: Ruff format" {
            Set-Location $intelDir
            python -m ruff format --check src/ tests/
        }
        Run-Check "Intelligence: Mypy" {
            Set-Location $intelDir
            python -m mypy src/
        }
        Run-Check "Intelligence: Pytest" {
            Set-Location $intelDir
            python -m pytest tests/ -v --tb=short
        }
    }
}

# ============================================================
# Frontend
# ============================================================
if (-not $SkipFrontend) {
    $frontendDir = Join-Path $repoRoot "frontend"
    if (Test-Path (Join-Path $frontendDir "package.json")) {
        Write-Header "Frontend"

        $nodeAvailable = $null -ne (Get-Command node -ErrorAction SilentlyContinue)
        if (-not $nodeAvailable) {
            # Try common install locations
            $nodePath = "C:\Program Files\nodejs\node.exe"
            if (Test-Path $nodePath) {
                $env:PATH = "C:\Program Files\nodejs;" + $env:PATH
                $nodeAvailable = $true
            }
        }

        if ($nodeAvailable) {
            Run-Check "Frontend: npm install" {
                Set-Location $frontendDir
                npm install --silent
            }
            Run-Check "Frontend: ESLint" {
                Set-Location $frontendDir
                npm run lint
            }
            Run-Check "Frontend: TypeScript check" {
                Set-Location $frontendDir
                npm run typecheck
            }
            if (-not $Quick) {
                Run-Check "Frontend: Tests" {
                    Set-Location $frontendDir
                    npm run test -- --run
                }
                Run-Check "Frontend: Build" {
                    Set-Location $frontendDir
                    npm run build
                }
            }
        } else {
            Write-Host "  [WARN] node not found - skipping frontend checks" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [INFO] Frontend not yet scaffolded - skipping" -ForegroundColor Gray
    }
}

# ============================================================
# Summary
# ============================================================
Set-Location $repoRoot
Write-Header "Verification Summary"
Write-Host ""
Write-Host "PASSED ($($script:passed.Count)):" -ForegroundColor Green
$script:passed | ForEach-Object { Write-Host "  + $_" -ForegroundColor Green }

if ($script:failures.Count -gt 0) {
    Write-Host ""
    Write-Host "FAILED ($($script:failures.Count)):" -ForegroundColor Red
    $script:failures | ForEach-Object { Write-Host "  x $_" -ForegroundColor Red }
    Write-Host ""
    Write-Host "DO NOT COMMIT. Fix all failures first." -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "All checks passed. Safe to commit." -ForegroundColor Green
    exit 0
}
