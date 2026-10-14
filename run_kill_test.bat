@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
chcp 65001 >nul
set PYTHONUTF8=1
set "VPY=%ROOT%\.venv\Scripts\python.exe"
if exist "%VPY%" goto :have_venv
echo Setup has not been run yet. Double-click setup.bat first.
pause
exit /b 1
:have_venv

echo.
echo ==== Profile Twins: kill test (21 candidates, Sonnet, about 10 min) ====
echo.
if defined ANTHROPIC_API_KEY goto :have_key
echo Paste your Anthropic API key and press Enter.
echo It starts with sk-ant- . Create one at https://platform.claude.com/settings/keys
set /p "ANTHROPIC_API_KEY=Key: "
if not defined ANTHROPIC_API_KEY goto :no_key
choice /c YN /n /m "Save the key on this PC so you are not asked again? [Y/N] "
if errorlevel 2 goto :have_key
setx ANTHROPIC_API_KEY "%ANTHROPIC_API_KEY%" >nul
echo Saved to your Windows user environment variables.
:have_key

"%VPY%" -m twins all --quick --yes
if errorlevel 1 goto :failed
if not exist "%ROOT%\run_quick\results\index.html" goto :failed
start "" "%ROOT%\run_quick\results\index.html"
if exist "%ROOT%\run_quick\app\index.html" start "" "%ROOT%\run_quick\app\index.html"
echo.
echo Done. The report has opened in your browser.
echo Files: run_quick\results\index.html and run_quick\results\report.md
echo.
pause
exit /b 0

:no_key
echo No key entered.
pause
exit /b 1

:failed
echo.
echo The run stopped. If it was interrupted, double-click this file again: finished calls are cached and not paid for twice.
echo Full log: run_quick\run_log.txt
echo.
pause
exit /b 1
