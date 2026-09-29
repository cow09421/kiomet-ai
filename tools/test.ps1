$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:TEMP = Join-Path $projectRoot 'runtime\tmp'
$env:TMP = $env:TEMP
$testDirectory = Join-Path $projectRoot ('runtime\tmp\pytest-' + [guid]::NewGuid().ToString('N'))
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -m pytest (Join-Path $projectRoot 'tests') -c (Join-Path $projectRoot 'pyproject.toml') "--basetemp=$testDirectory" -q
exit $LASTEXITCODE
