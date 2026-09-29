param([string]$Python)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
foreach ($folder in @('runtime\tmp','runtime\cache\pip','runtime\browsers','runtime\browser-profile','runtime\logs','runtime\state','runtime\screenshots')) {
    New-Item -ItemType Directory -Path (Join-Path $projectRoot $folder) -Force | Out-Null
}
$env:PYTHONUTF8 = '1'
$env:TEMP = Join-Path $projectRoot 'runtime\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $projectRoot 'runtime\cache\pip'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $projectRoot 'runtime\browsers'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (-not $Python) {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command) { $Python = $command.Source }
    }
    if (-not $Python) { throw '請以 -Python 指定 Python 3.12 以上版本的 python.exe 路徑。' }
    & $Python -c 'import sys; assert sys.version_info >= (3,12), "Python 版本至少需要 3.12"'
    if ($LASTEXITCODE -ne 0) { throw '基礎 Python 版本不符合要求。' }
    & $Python -m venv (Join-Path $projectRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw '建立獨立環境失敗。' }
}
& $pythonExe -m pip install -r (Join-Path $projectRoot 'requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw '套件安裝失敗。' }
& $pythonExe -m playwright install chromium --no-shell
if ($LASTEXITCODE -ne 0) { throw '專用瀏覽器安裝失敗。' }
Write-Output '完成。請回到專案根目錄執行 .\run.ps1'
