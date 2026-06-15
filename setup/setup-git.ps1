# setup-git.ps1 — one-shot git initialization for Project Gamma (run on Windows).
#
# WHY THIS IS A SCRIPT YOU RUN (not done for you): the Cowork Linux sandbox mounts
# this folder over FUSE, which forbids the unlink/rename operations git needs — git
# literally corrupts its own config there. Git must run natively on Windows.
#
# Safe to re-run. Secrets are already gitignored (.mcp.json stays on disk, untracked).
# PowerShell 5.1 compatible. Review before running.

$ErrorActionPreference = "Stop"
Set-Location "C:\Users\jackw\Desktop\42"

# 1. Remove the broken half-initialized .git the sandbox left behind (if present).
if (Test-Path ".git") {
    Write-Host "Removing partial .git from the sandbox attempt..."
    Remove-Item -Recurse -Force ".git"
}

# 2. Initialize.
git init
git branch -M main
git config user.email "jack.watergun@gmail.com"
git config user.name "Swjsh"

# 3. Safety check: confirm no secret is about to be tracked BEFORE committing.
git add -A
$leak = git grep -nE "9EzmHpix|ELWu7Qjb|PYwDLKk2YbQdiC6SrKuo4zWjvHx577iqSz6LpNwef8Y" -- ':!*.example' 2>$null
if ($leak) {
    Write-Host "ABORT: a secret appears in tracked files:" -ForegroundColor Red
    Write-Host $leak
    Write-Host "Fix the file, then re-run. (Nothing was committed.)"
    exit 1
}

# 4. Sanity: tracked file count should be a few thousand, NOT ~24,000 (venvs/data excluded).
$count = (git ls-files | Measure-Object).Count
Write-Host "Tracked files: $count  (expect low thousands; if ~24k, .gitignore is wrong)"

# 5. Baseline commit.
git commit -m "baseline: Project Gamma snapshot + OP-11 shadow-loop bugfixes, secrets externalized"

# 6. Connect the remote and push (you must be authenticated to GitHub).
#    If 'origin' already exists this is a no-op; otherwise it is added.
if (-not (git remote | Select-String -Quiet "origin")) {
    git remote add origin "https://github.com/Swjsh/42.git"
}
Write-Host ""
Write-Host "Ready to push. Run:  git push -u origin main" -ForegroundColor Green
Write-Host "(Requires a GitHub Personal Access Token or credential helper.)"
