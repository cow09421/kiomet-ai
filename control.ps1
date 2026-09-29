param([ValidateSet('pause','resume','stop','status')][string]$Command = 'status')
$ErrorActionPreference = 'Stop'
$control = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime\state\control.json') -Raw | ConvertFrom-Json
if ($Command -eq 'status') { Invoke-RestMethod -Uri "$($control.url)/api/status" | ConvertTo-Json -Depth 12 }
else { Invoke-RestMethod -Uri "$($control.url)/api/$Command" -Method Post -Headers @{'X-Control-Token'=$control.token} | ConvertTo-Json }
