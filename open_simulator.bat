@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
chcp 65001 >nul
set PYTHONUTF8=1
set "VPY=%ROOT%\.venv\Scripts\python.exe"
rem Build the research-queue simulator from saved screener labels and open it. No API calls, no cost.
set "DONE="
if exist "%ROOT%\run\results.jsonl" (
  "%VPY%" -m twins app
  start "" "%ROOT%\run\app\index.html"
  set "DONE=1"
)
if not defined DONE if exist "%ROOT%\run_quick\results.jsonl" (
  "%VPY%" -m twins app --quick
  start "" "%ROOT%\run_quick\app\index.html"
  set "DONE=1"
)
if not defined DONE (
  if exist "%ROOT%\site\index.html" (
    start "" "%ROOT%\site\index.html"
  ) else (
    echo No finished runs yet. Run run_kill_test.bat first.
  )
)
echo.
pause
