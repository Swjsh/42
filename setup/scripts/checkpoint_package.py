"""checkpoint_package.py -- GOAL-CHECKPOINT-REDUCTION-PACKAGES-2026-09-05 K2.

Scaffolds a checkpoint-packet reduction package folder so authoring the second, third,
... package is mechanical rather than hand-rolled each time (the way
analysis/recommendations/packages/score-ladder-v2-shadow-retirement/ was built by hand
under K1).

CLI:
    python setup/scripts/checkpoint_package.py new <row-id> [--force]

Creates `analysis/recommendations/packages/<row-id>/`:
    README.md      -- template with the sections a package README must have
                       (packet row id, prereg, organs table, patch summary, revert
                       line, RED-proof block, "nothing applied" line)
    apply.ps1       -- template that applies change.patch, unregisters/tombstones
                       whatever the package names, runs guard_test.py +
                       backtest/tests/run_safety_gate.py, refuses without
                       $env:GAMMA_FREEZE_OVERRIDE=1, supports -DryRun
    guard_test.py   -- template with a main() that returns non-zero until the
                       author fills in real assertions (so an unfinished scaffold is
                       loud, never silently green)
    change.patch    -- empty placeholder (0 bytes); the author fills this in via
                       `git diff` after making + capturing + reverting the real edit,
                       exactly as K1 did.

Never applies anything, never touches FROZEN_TRADING_PATH, never registers/unregisters
a real scheduled task. $0, stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGES_DIR = REPO / "analysis" / "recommendations" / "packages"

_ROW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}[a-z0-9]$")


def _validate_row_id(row_id: str) -> None:
    if not _ROW_ID_RE.match(row_id):
        raise ValueError(
            f"row-id {row_id!r} must be lowercase, hyphenated, 3-82 chars "
            "(matching a checkpoint-inventory row_id)"
        )


README_TEMPLATE = """# Package: {row_id}

**Packet row:** `{row_id}` in `analysis/recommendations/checkpoint-2026-09-29-inventory.json`.
**Verdict at authoring time:** <PASTE from `python setup/scripts/checkpoint_packet.py` stdout>
**Prereg:** <path> -- status <status>.

## What this retires / changes

<Name every organ this package touches: scheduled task(s), installer script(s), the
ledger writer, the ledger path, the guard test that already exists, cockpit tiles or
readers left alone, and confirm which params keys (if any) are touched -- FROZEN
params-key edits must be called out explicitly and only applied 2026-09-29 with
GAMMA_FREEZE_OVERRIDE per the goal's OPERATING RULES.>

| Organ | Path |
|---|---|
| Scheduled task | `TODO` |
| Installer | `TODO` |
| Ledger writer | `TODO` |
| Ledger | `TODO` |
| Existing guard | `TODO` |
| Params keys touched | `TODO -- NONE, or name them + note FREEZE gating` |

## The patch

`change.patch` (from `git diff` against HEAD, captured then reverted -- HEAD's working
tree is unchanged by authoring this package):

<Describe each file the patch touches and why.>

## Revert

```
git revert <sha-of-the-applying-commit>
<any installer re-run needed to restore a scheduled task>
```

## RED-proof (quote verbatim, this session)

**Pre-patch:**
```
TODO -- paste guard_test.py output run against HEAD (before the patch)
```

**Post-patch (applied to a scratch worktree or the working tree, then reverted before
ending the session -- never left applied):**
```
TODO -- paste guard_test.py output run with the patch applied
```

## Nothing applied

`change.patch` was captured via `git diff`, then the working-tree edits were reverted
with `git checkout -- <files>` before this README was finalized. Verify:
`git status --porcelain -- <files>` is empty.
"""

APPLY_PS1_TEMPLATE = """#requires -Version 5.1
<#
.SYNOPSIS
  Applies the {row_id} package (packet row `{row_id}`). CONFIG FREEZE: refuses unless
  $env:GAMMA_FREEZE_OVERRIDE = "1". -DryRun prints the plan and changes nothing.
#>
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Repo = "{repo}"
$PkgDir = $PSScriptRoot
$Patch = Join-Path $PkgDir "change.patch"
$Python = Join-Path $Repo "backtest\\.venv\\Scripts\\python.exe"

$plan = @(
    "1. git apply `"$Patch`"",
    "2. <TODO: Unregister-ScheduledTask / other organ-specific stop action, if any>",
    "3. $Python `"$PkgDir\\guard_test.py`"  -- refuse (git apply -R the patch) if non-zero exit",
    "4. $Python backtest\\tests\\run_safety_gate.py  -- refuse if non-zero exit",
    "5. Report APPLIED only if 3 and 4 both exit 0"
)

if ($DryRun) {{
    Write-Output "DRY RUN -- plan only, nothing on disk or in Task Scheduler changes:"
    $plan | ForEach-Object {{ Write-Output "  $_" }}
    exit 0
}}

if ($env:GAMMA_FREEZE_OVERRIDE -ne "1") {{
    Write-Error "CONFIG FREEZE (2026-08-31 -> 2026-10-30): refusing to apply without `$env:GAMMA_FREEZE_OVERRIDE = '1'`."
    exit 2
}}

if (-not (Test-Path $Patch)) {{ Write-Error "Patch not found: $Patch"; exit 1 }}
if ((Get-Item $Patch).Length -eq 0) {{ Write-Error "change.patch is still the empty scaffold placeholder -- fill it in before applying."; exit 1 }}

Push-Location $Repo
try {{
    Write-Output "Applying $Patch ..."
    git apply $Patch
    if ($LASTEXITCODE -ne 0) {{ throw "git apply failed (exit $LASTEXITCODE)" }}

    # TODO: organ-specific stop action (e.g. Unregister-ScheduledTask -TaskName ... -Confirm:$false)

    Write-Output "Running guard_test.py ..."
    & $Python (Join-Path $PkgDir "guard_test.py")
    if ($LASTEXITCODE -ne 0) {{
        Write-Error "guard_test.py is RED -- reverting patch."
        git apply -R $Patch
        exit 1
    }}

    Write-Output "Running backtest/tests/run_safety_gate.py ..."
    & $Python (Join-Path $Repo "backtest\\tests\\run_safety_gate.py")
    if ($LASTEXITCODE -ne 0) {{
        Write-Error "run_safety_gate.py is RED -- reverting patch."
        git apply -R $Patch
        exit 1
    }}

    Write-Output "APPLIED: {row_id}"
}}
finally {{
    Pop-Location
}}
"""

GUARD_TEST_TEMPLATE = '''"""guard_test.py -- guard for the {row_id} package. SCAFFOLD -- fill in real
assertions before this package is usable; main() intentionally returns 1 (RED) until
you do, so an unfinished scaffold can never be mistaken for a passing guard.

Packet row: {row_id}.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def test_scaffold_not_yet_implemented() -> None:
    raise AssertionError(
        "{row_id}/guard_test.py is still the K2 scaffold -- replace this with real "
        "assertions (organ absence + ledger-stops-growing, per the goal's DONE-WHEN) "
        "before this package can be applied."
    )


def main() -> int:
    try:
        test_scaffold_not_yet_implemented()
        print("[PASS] test_scaffold_not_yet_implemented")
        return 0
    except AssertionError as exc:
        print(f"[FAIL] test_scaffold_not_yet_implemented -- {{exc}}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def new_package(row_id: str, force: bool = False) -> Path:
    _validate_row_id(row_id)
    pkg_dir = PACKAGES_DIR / row_id
    if pkg_dir.exists() and not force:
        raise FileExistsError(f"{pkg_dir} already exists (pass --force to overwrite templates)")
    pkg_dir.mkdir(parents=True, exist_ok=True)

    (pkg_dir / "README.md").write_text(README_TEMPLATE.format(row_id=row_id), encoding="utf-8")
    (pkg_dir / "apply.ps1").write_text(
        APPLY_PS1_TEMPLATE.format(row_id=row_id, repo=str(REPO)), encoding="utf-8"
    )
    (pkg_dir / "guard_test.py").write_text(GUARD_TEST_TEMPLATE.format(row_id=row_id), encoding="utf-8")
    patch_path = pkg_dir / "change.patch"
    if not patch_path.exists() or force:
        patch_path.write_text("", encoding="utf-8")
    return pkg_dir


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    new_ap = sub.add_parser("new", help="scaffold a new package folder")
    new_ap.add_argument("row_id")
    new_ap.add_argument("--force", action="store_true", help="overwrite existing template files")
    args = ap.parse_args(argv)

    if args.cmd == "new":
        try:
            pkg_dir = new_package(args.row_id, force=args.force)
        except (ValueError, FileExistsError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"OK: scaffolded {pkg_dir.relative_to(REPO)}")
        for name in ("README.md", "apply.ps1", "guard_test.py", "change.patch"):
            print(f"  {(pkg_dir / name).relative_to(REPO)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
