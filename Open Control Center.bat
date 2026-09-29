@echo off
rem Kiomet AI Control Center（控制中心）啟動入口：雙擊即開，唯讀監控，不影響平台。
setlocal
set "PROJECT=%~dp0"
set "PYW=%PROJECT%.venv\Scripts\pythonw.exe"
set "PY=%PROJECT%.venv\Scripts\python.exe"
if exist "%PYW%" (
  start "" /MIN "%PYW%" "%PROJECT%tools\control_center.py"
) else (
  start "" /MIN "%PY%" "%PROJECT%tools\control_center.py"
)
endlocal
