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
echo ==== Under Pressure (approved run, no cost prompt; hard stop at $25): 96 agent runs plus the email monitor, about 30-45 min ====
echo.
echo Checking everything works with a fake model first (free, a few seconds)...
"%VPY%" -m pressure all --mock --seeds 1 --workdir "%ROOT%\run_pressure_mock" > "%ROOT%\run_pressure_selftest.txt" 2>&1
if errorlevel 1 goto :selftest_failed
echo Self-test passed.
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

"%VPY%" -m pressure all --yes
if errorlevel 1 goto :failed
if not exist "%ROOT%\run_pressure\results\index.html" goto :stopped

powershell -NoProfile -Command "Compress-Archive -Force -Path '%ROOT%\run_pressure\runs.jsonl','%ROOT%\run_pressure\monitor.jsonl','%ROOT%\run_pressure\monitor_items.json','%ROOT%\run_pressure\config.json','%ROOT%\run_pressure\run_log.txt' -DestinationPath '%ROOT%\run_pressure_for_claude.zip'" >nul 2>&1
start "" "%ROOT%\run_pressure\results\index.html"
echo.
echo Done. The results page has opened in your browser.
echo For Claude: run_pressure_for_claude.zip (in this folder) has everything needed to analyse the run.
echo.
pause
exit /b 0

:selftest_failed
echo.
echo The self-test failed, so nothing was sent to the API and nothing was spent.
echo Details: run_pressure_selftest.txt (send it to Claude).
echo.
pause
exit /b 1

:no_key
echo No key entered.
pause
exit /b 1

:stopped
echo.
echo Stopped before finishing (or you answered N). Nothing more will be spent.
echo Double-click this file again to continue: finished calls are cached and not paid for twice.
echo Log: run_pressure\run_log.txt
echo.
pause
exit /b 1

:failed
echo.
echo The run stopped with an error. Double-click this file again to continue: finished calls are cached.
echo Log: run_pressure\run_log.txt (send it to Claude).
echo.
pause
exit /b 1
