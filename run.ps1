param([switch]$NoBrowser, [double]$Duration = 0, [switch]$ExitAfterStop, [int]$Port = 8765, [switch]$Live, [switch]$NoCapture, [switch]$LiveAuthorize)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw '請先執行 .\tools\setup.ps1' }
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $projectRoot 'runtime\browsers'
$env:TEMP = Join-Path $projectRoot 'runtime\tmp'
$env:TMP = $env:TEMP
$argsList = @('-m', 'kiomet_ai.app', '--port', "$Port", '--duration', "$Duration")
if ($NoBrowser) { $argsList += '--no-browser' }
if ($ExitAfterStop) { $argsList += '--exit-after-stop' }
if ($Live) { $argsList += '--live' }
if ($NoCapture) { $argsList += '--no-capture' }
if ($LiveAuthorize) { $argsList += '--live-authorize' }
& $pythonExe @argsList
exit $LASTEXITCODE
