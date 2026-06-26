#requires -Version 5.1
<#
.SYNOPSIS
  Install the Gamma safety-gate git hooks (Phase 2 of the autonomy plan).
.DESCRIPTION
  Copies setup/git-hooks/pre-commit -> .git/hooks/pre-commit so every commit (J's,
  the conductor's, the actuator's) is gated by the fast curated safety suite. The hook
  is bypassable (git commit --no-verify) and fail-fast (~2s). Re-run any time to refresh.
#>
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$src = Join-Path $PSScriptRoot "git-hooks\pre-commit"
$hooksDir = Join-Path $repo ".git\hooks"
if (-not (Test-Path $src)) { Write-Error "hook source missing: $src"; exit 1 }
if (-not (Test-Path $hooksDir)) { Write-Error "no .git/hooks dir at $hooksDir (is this a git repo?)"; exit 1 }
$dst = Join-Path $hooksDir "pre-commit"
Copy-Item -LiteralPath $src -Destination $dst -Force
# Make sure git (via its bundled sh) treats it as executable on checkout-less Windows.
Write-Output "OK: installed pre-commit safety-gate hook -> $dst"
Write-Output "    Runs the fast curated gate (~2s) on every commit. Bypass: git commit --no-verify"
