@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
chcp 65001 >nul
set PYTHONUTF8=1
set "VPY=%ROOT%\.venv\Scripts\python.exe"
rem Rebuild the results pages from saved results. No API calls, no cost.
set "DONE="
if exist "%ROOT%\run_quick\results.jsonl" (
  "%VPY%" -m twins report --quick
  start "" "%ROOT%\run_quick\results\index.html"
  set "DONE=1"
)
if exist "%ROOT%\run\results.jsonl" (
  "%VPY%" -m twins report
  start "" "%ROOT%\run\results\index.html"
  set "DONE=1"
)
if not defined DONE echo No finished runs yet. Run run_kill_test.bat first.
echo.
pause
