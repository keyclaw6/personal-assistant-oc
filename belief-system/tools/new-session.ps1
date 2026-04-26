param(
  [string]$BeliefSlug = "unassigned",
  [string]$Mode = "belief_session"
)

$Root = Split-Path -Parent $PSScriptRoot
$SessionId = "$(Get-Date -Format 'yyyyMMdd-HHmmss')-$BeliefSlug"
$SessionDir = Join-Path $Root "04_sessions/$SessionId"
New-Item -ItemType Directory -Force -Path $SessionDir | Out-Null

$manifest = Get-Content (Join-Path $Root "_system/templates/session_manifest.json") -Raw
$manifest = $manifest.Replace('"session_id": ""', '"session_id": "' + $SessionId + '"')
$manifest = $manifest.Replace('"date": ""', '"date": "' + (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK') + '"')
$manifest = $manifest.Replace('"mode": "belief_session"', '"mode": "' + $Mode + '"')
$manifest = $manifest.Replace('"belief_slug": ""', '"belief_slug": "' + $BeliefSlug + '"')
Set-Content -Path (Join-Path $SessionDir "00_manifest.json") -Value $manifest -Encoding UTF8

Copy-Item (Join-Path $Root "_system/templates/session_transcript.md") (Join-Path $SessionDir "01_transcript.md")
Copy-Item (Join-Path $Root "_system/templates/context_loaded.md") (Join-Path $SessionDir "02_context_loaded.md")
Copy-Item (Join-Path $Root "_system/templates/interpretive_analysis.md") (Join-Path $SessionDir "03_interpretive_analysis.md")
Copy-Item (Join-Path $Root "_system/templates/deterministic_clarification.json") (Join-Path $SessionDir "04_deterministic_clarification.json")
Copy-Item (Join-Path $Root "_system/templates/belief_updates.md") (Join-Path $SessionDir "05_belief_updates.md")
Copy-Item (Join-Path $Root "_system/templates/next_actions.md") (Join-Path $SessionDir "06_next_actions.md")
New-Item -ItemType File -Force -Path (Join-Path $SessionDir "07_audit.md") | Out-Null

Write-Output $SessionDir
