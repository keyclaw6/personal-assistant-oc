param(
  [Parameter(Mandatory = $true)]
  [string]$Slug,
  [string]$Status = "candidate"
)

$Root = Split-Path -Parent $PSScriptRoot
$Folder = Join-Path $Root "03_beliefs/$Status/$Slug"
New-Item -ItemType Directory -Force -Path $Folder | Out-Null

$content = Get-Content (Join-Path $Root "_system/templates/belief.md") -Raw
$today = Get-Date -Format 'yyyy-MM-dd'
$content = $content -replace '(?m)^slug:\s*$', "slug: $Slug"
$content = $content -replace '(?m)^status:\s*candidate\s*$', "status: $Status"
$content = $content -replace '(?m)^created:\s*$', "created: $today"
$content = $content -replace '(?m)^updated:\s*$', "updated: $today"

Set-Content -Path (Join-Path $Folder "belief.md") -Value $content -Encoding UTF8
Write-Output $Folder
