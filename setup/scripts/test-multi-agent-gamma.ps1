# ============================================================================
# Project Gamma -- Multi-Agent Gamma 2.0 Smoke Test Harness
# ============================================================================
#
# RUN THIS AFTER ANY CHANGE TO MULTI-AGENT GAMMA 2.0 INFRASTRUCTURE.
#
# Validates everything shipped in the 2026-05-09 Multi-Agent Gamma 2.0 batch:
#   - PowerShell scripts parse cleanly
#   - Python modules import cleanly
#   - All cross-referenced files exist
#   - Function inventory matches expectations
#   - Live integration test: Invoke-Claude end-to-end with a no-op prompt
#   - PID lockfile creation/cleanup cycle
#   - State digest produces valid output
#   - State hash is deterministic
#
# Exit code: 0 on full pass, 1 on any failure.
# Cost: ~$0.01 per run (one trivial Haiku call). ~5 sec wall-clock.
#
# Usage:
#   .\setup\scripts\test-multi-agent-gamma.ps1
#   .\setup\scripts\test-multi-agent-gamma.ps1 -SkipLive   # skip the $0.01 claude call
#   .\setup\scripts\test-multi-agent-gamma.ps1 -Verbose
#
# Recommended cadence: run before every git commit, after every harness edit,
# after any operating-principle 15 doctrine update.
# ============================================================================

[CmdletBinding()]
param(
    [switch]$SkipLive
)

$WorkDir = "C:\Users\jackw\Desktop\42"
$totalChecks = 0
$failedChecks = 0
$failures = @()

function Test-Check {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    $script:totalChecks++
    try {
        $result = & $Block
        if ($result -eq $false -or ($null -eq $result -and $LASTEXITCODE -ne 0)) {
            $script:failedChecks++
            $script:failures += $Name
            Write-Output "  FAIL  $Name"
        } else {
            Write-Output "  OK    $Name"
        }
    } catch {
        $script:failedChecks++
        $script:failures += "$Name -- $($_.Exception.Message)"
        Write-Output "  FAIL  $Name -- $($_.Exception.Message)"
    }
}

Write-Output "============================================================"
Write-Output "  Multi-Agent Gamma 2.0 Smoke Test Harness"
Write-Output "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "============================================================"

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[1/8] PowerShell parse (ALL .ps1 in repo + setup/)"
# ---------------------------------------------------------------------------
# Scan EVERY .ps1 in the repo, not just Multi-Agent Gamma 2.0 files.
# Catches em-dash regressions like the one that broke run-eod-summary.ps1
# and install-tasks.ps1 before they fired in production.
$allPs1 = Get-ChildItem -Path $WorkDir -Filter "*.ps1" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\\.venv\\" -and $_.FullName -notmatch "\\node_modules\\" }
foreach ($ps1 in $allPs1) {
    $relPath = $ps1.FullName.Substring($WorkDir.Length + 1)
    Test-Check -Name "parse $relPath" -Block {
        $errors = @()
        [System.Management.Automation.Language.Parser]::ParseFile($ps1.FullName, [ref]$null, [ref]$errors) | Out-Null
        return ($errors.Count -eq 0)
    }
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[2/8] Python imports + syntax"
# ---------------------------------------------------------------------------
$venv = Join-Path $WorkDir "backtest\.venv\Scripts\python.exe"
$pyChecks = @(
    @{ Name = "import autoresearch.parallel_eval"; Cmd = "from autoresearch import parallel_eval; assert parallel_eval.MAX_PARALLEL_WORKERS == 4" },
    @{ Name = "import autoresearch.random_eval";    Cmd = "from autoresearch import random_eval" },
    @{ Name = "import autoresearch.runner";         Cmd = "from autoresearch import runner" },
    @{ Name = "import autoresearch.aggregate_random"; Cmd = "from autoresearch import aggregate_random" },
    @{ Name = "import autoresearch.synthesize_v15"; Cmd = "from autoresearch import synthesize_v15" },
    @{ Name = "compile pressure_tests/conftest.py"; Cmd = "import py_compile; py_compile.compile('tests/pressure_tests/conftest.py', doraise=True)" },
    @{ Name = "compile pressure_tests/examples/test_template.py"; Cmd = "import py_compile; py_compile.compile('tests/pressure_tests/examples/test_template.py', doraise=True)" }
)
Push-Location (Join-Path $WorkDir "backtest")
try {
    foreach ($check in $pyChecks) {
        Test-Check -Name $check.Name -Block {
            $output = & $venv -c $check.Cmd 2>&1
            return ($LASTEXITCODE -eq 0)
        }
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[3/8] Doctrine + prompt files exist + non-empty"
# ---------------------------------------------------------------------------
$expectedFiles = @(
    "docs\plans\multi-agent-gamma.md",
    "doctrine\rules-as-gates.md",
    "doctrine\iron-law-trades.md",
    "doctrine\rationalization-counters.md",
    "automation\prompts\eod-orchestrator.md",
    "automation\prompts\eod-workers\01-metrics-and-grading.md",
    "automation\prompts\eod-workers\02-predictions-and-audit.md",
    "automation\prompts\eod-workers\03-chart-walks.md",
    "automation\prompts\eod-workers\04-shadow-and-darkpool.md",
    "automation\prompts\adversarial-review.md",
    "automation\prompts\param-promotion-spec-review.md",
    "automation\prompts\param-promotion-quality-review.md",
    "backtest\tests\pressure_tests\README.md",
    "backtest\tests\pressure_tests\conftest.py",
    "backtest\tests\pressure_tests\examples\test_template.py"
)
foreach ($rel in $expectedFiles) {
    $path = Join-Path $WorkDir $rel
    Test-Check -Name "exists+nonempty $rel" -Block {
        return ((Test-Path $path) -and ((Get-Item $path).Length -gt 100))
    }
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[4/8] _shared.ps1 function inventory"
# ---------------------------------------------------------------------------
. (Join-Path $WorkDir "setup\scripts\_shared.ps1")
$expectedFns = @('Get-EtNow','Repair-StateFiles','Stop-ProcessTree','Stop-StaleClaudeProcesses','Invoke-Claude','Test-DiskSpaceAvailable','Test-WeekDay','Test-MarketHours','Test-HolidayFromAlpaca','Write-TaskLog')
foreach ($fn in $expectedFns) {
    Test-Check -Name "function $fn defined" -Block {
        return ($null -ne (Get-Command $fn -ErrorAction SilentlyContinue))
    }
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[5/8] State digest + hash"
# ---------------------------------------------------------------------------
Test-Check -Name "session-start-digest -Markdown emits 'STATE DIGEST'" -Block {
    $digest = & (Join-Path $WorkDir "setup\scripts\session-start-digest.ps1") -Markdown 2>$null | Out-String
    return ($digest -match "STATE DIGEST" -and $digest -match "Rule version")
}
Test-Check -Name "session-start-digest JSON parses" -Block {
    $json = & (Join-Path $WorkDir "setup\scripts\session-start-digest.ps1") 2>$null | Out-String
    $parsed = $json | ConvertFrom-Json -ErrorAction Stop
    return ($null -ne $parsed.rule_version)
}
Test-Check -Name "compute-state-hash returns 16 hex chars" -Block {
    $h = & (Join-Path $WorkDir "setup\scripts\compute-state-hash.ps1") 2>$null
    return ($h -match "^[0-9a-f]{16}$")
}
Test-Check -Name "compute-state-hash is deterministic" -Block {
    $h1 = & (Join-Path $WorkDir "setup\scripts\compute-state-hash.ps1") 2>$null
    $h2 = & (Join-Path $WorkDir "setup\scripts\compute-state-hash.ps1") 2>$null
    return ($h1 -eq $h2)
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[6/8] Repair-StateFiles smoke"
# ---------------------------------------------------------------------------
Test-Check -Name "Repair-StateFiles validates current state" -Block {
    $r = Repair-StateFiles -TaskName "smoke-harness"
    return ($r.Validated -gt 0 -and $r.Unrecoverable -eq 0)
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[7/8] Pytest collection (no execution)"
# ---------------------------------------------------------------------------
Push-Location (Join-Path $WorkDir "backtest")
try {
    Test-Check -Name "pytest collects pressure_tests cleanly" -Block {
        $output = & $venv -m pytest tests/pressure_tests/ --collect-only --no-header -q 2>&1
        return ($LASTEXITCODE -eq 0 -and ($output -join " ") -match "tests collected")
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "[8/8] Live Invoke-Claude integration test"
# ---------------------------------------------------------------------------
if ($SkipLive) {
    Write-Output "  SKIP (--SkipLive flag set; saves ~`$0.01)"
} else {
    Test-Check -Name "Invoke-Claude end-to-end (smoke-prompt)" -Block {
        $smokePrompt = Join-Path $WorkDir "setup\scripts\smoke-prompt.md"
        if (-not (Test-Path $smokePrompt)) {
            "# Smoke`n`nOutput one line: SMOKE_OK et={runtime ET time}`nThen exit. No tools." |
                Out-File -FilePath $smokePrompt -Encoding utf8
        }
        $exit = Invoke-Claude `
            -PromptFile $smokePrompt `
            -TaskName "smoke-harness" `
            -MaxBudgetUsd 0.10 `
            -Model "haiku" `
            -TimeoutSec 60 `
            -Effort "low"
        return ($exit -eq 0)
    }
    Test-Check -Name "PID lockfile released after smoke" -Block {
        $pidFile = Join-Path $WorkDir "automation\state\smoke-harness.pid"
        return (-not (Test-Path $pidFile))
    }
}

# ---------------------------------------------------------------------------
Write-Output ""
Write-Output "============================================================"
$passed = $totalChecks - $failedChecks
Write-Output "  RESULT: $passed/$totalChecks checks passed"
if ($failedChecks -gt 0) {
    Write-Output ""
    Write-Output "  FAILURES:"
    foreach ($f in $failures) { Write-Output "    - $f" }
    Write-Output "============================================================"
    exit 1
} else {
    Write-Output "  ALL GREEN"
    Write-Output "============================================================"
    exit 0
}
