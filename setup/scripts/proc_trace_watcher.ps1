#requires -Version 5.1
<#
.SYNOPSIS
  Event-driven process-creation watcher, spawned hidden by proc_trace.py
  (GOAL-SILENT-RIG-2026-09-05 R4a). NOT meant to be run interactively or registered as a
  scheduled task on its own -- proc_trace.py (and, at one more remove,
  proc_trace_keepalive.py / Gamma_ProcTraceKeepalive) owns this process's lifecycle.

.DESCRIPTION
  Subscribes to WMI's own __InstanceCreationEvent for Win32_Process via
  Register-CimIndicationEvent -- event-driven (WMI delivers a notification the instant a
  process is created, at up to 0.2s granularity), never a poll-the-process-table loop.
  For each new process, immediately (same event tick, before the new process OR its parent
  can exit) looks up the parent's Name/CommandLine via Get-CimInstance and emits ONE compact
  JSON line to stdout: {ts_local (ms), pid, ppid, name, cmdline, parent_name,
  parent_cmdline, session_id}.

  Writes nothing to disk itself -- proc_trace.py (the parent Python process that spawned
  this script hidden, stdout piped) owns file rotation/capping. This script's only job is
  "notice a process was created, name it and its parent, print one line, forever."

  Never throws out of the loop: any per-event lookup failure (parent already exited,
  transient WMI hiccup) is caught and the row is still emitted with parent_name/
  parent_cmdline = $null rather than skipping the row entirely -- SOME record (even
  parent-less) is better than a silent gap in the trace.
#>
$ErrorActionPreference = "SilentlyContinue"
$sourceId = "GammaProcTraceCreate"

# Clean up any stale registration from a previous crashed run of this same script under this
# session (Register-CimIndicationEvent errors if the SourceIdentifier is already in use).
Get-EventSubscriber -SourceIdentifier $sourceId -ErrorAction SilentlyContinue | Unregister-Event -ErrorAction SilentlyContinue

$query = "SELECT * FROM __InstanceCreationEvent WITHIN 0.2 WHERE TargetInstance ISA 'Win32_Process'"
Register-CimIndicationEvent -Query $query -SourceIdentifier $sourceId | Out-Null

try {
    while ($true) {
        # Wait-Event blocks until WMI delivers a queued event OR the timeout elapses -- this
        # is NOT polling the process table; it is servicing the PowerShell event queue that
        # Register-CimIndicationEvent (itself event-driven) feeds. The timeout exists only so
        # this loop periodically re-checks for external termination (parent process closing
        # our stdout pipe raises on Write-Output, which the outer proc_trace.py treats as
        # "child exited").
        $ev = Wait-Event -SourceIdentifier $sourceId -Timeout 5
        if ($null -eq $ev) { continue }
        Remove-Event -SourceIdentifier $sourceId -ErrorAction SilentlyContinue

        try {
            $newProc = $ev.SourceEventArgs.NewEvent.TargetInstance
            $childPid = [int]$newProc.ProcessId
            $ppid = [int]$newProc.ParentProcessId

            $parentName = $null
            $parentCmdline = $null
            try {
                $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$ppid" -ErrorAction SilentlyContinue
                if ($parent) {
                    $parentName = $parent.Name
                    $parentCmdline = $parent.CommandLine
                }
            } catch { }

            $row = [ordered]@{
                ts_local       = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
                pid            = $childPid
                ppid           = $ppid
                name           = $newProc.Name
                cmdline        = $newProc.CommandLine
                parent_name    = $parentName
                parent_cmdline = $parentCmdline
                session_id     = [int]$newProc.SessionId
            }
            $json = $row | ConvertTo-Json -Compress
            Write-Output $json
            [Console]::Out.Flush()
        } catch {
            # A single bad event must never kill the subscription -- next Wait-Event just
            # picks up the next process-creation event.
            continue
        }
    }
} finally {
    Unregister-Event -SourceIdentifier $sourceId -ErrorAction SilentlyContinue
}
