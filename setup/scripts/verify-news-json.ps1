#!/usr/bin/env pwsh
$json = Get-Content 'C:\Users\jackw\Desktop\42\automation\state\news.json' -Raw | ConvertFrom-Json
Write-Output ("for_session: " + $json.for_session)
Write-Output ("as_of: " + $json.as_of)
Write-Output ("regime: " + $json.regime)
Write-Output ("rule_version_active: " + $json.v15_first_session_notes.rule_version_active)
Write-Output ("first_live_session: " + $json.v15_first_session_notes.first_live_session)
Write-Output ("primary_catalyst: " + $json.primary_catalyst.type + " - " + $json.primary_catalyst.description.Substring(0, 80))
Write-Output ("vix_expectation_preview: " + $json.vix_expectation.Substring(0, 80))
Write-Output ("level_count: " + $json.key_levels_external.spy_relevant_levels_tomorrow.Count)
Write-Output "PARSE OK"
