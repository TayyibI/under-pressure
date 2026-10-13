@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%CD%"
chcp 65001 >nul
set PYTHONUTF8=1
set "LOG=%ROOT%\setup_log.txt"
echo Profile Twins setup log > "%LOG%"
echo %DATE% %TIME%>> "%LOG%"

echo.
echo ==== Profile Twins: one-time setup ====
echo.

echo [1/5] Looking for Python 3.10 or newer...
set "PY="
call :try_cmd py -3
if not defined PY call :try_cmd python
if not defined PY call :try_cmd python3
if not defined PY call :try_path "%USERPROFILE%\anaconda3\python.exe"
if not defined PY call :try_path "%USERPROFILE%\miniconda3\python.exe"
if not defined PY call :try_path "%LOCALAPPDATA%\anaconda3\python.exe"
if not defined PY call :try_path "%LOCALAPPDATA%\miniconda3\python.exe"
if not defined PY call :try_path "%ProgramData%\anaconda3\python.exe"
if not defined PY call :try_path "%ProgramData%\miniconda3\python.exe"
if not defined PY call :try_path "C:\anaconda3\python.exe"
for %%V in (314 313 312 311 310) do if not defined PY call :try_path "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
for %%V in (314 313 312 311 310) do if not defined PY call :try_path "C:\Python%%V\python.exe"
for %%V in (314 313 312 311 310) do if not defined PY call :try_path "%ProgramFiles%\Python%%V\python.exe"
if defined PY goto :found_py
echo     Could not find Python 3.10 or newer.
echo     Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run this again.
echo STEP1_NO_PYTHON>> "%LOG%"
goto :fail
:found_py
echo     Using: %PY%
echo USING_PYTHON %PY%>> "%LOG%"

echo [2/5] Creating a private Python environment in .venv ...
if exist ".venv\Scripts\python.exe" goto :venv_ok
%PY% -m venv .venv >> "%LOG%" 2>&1
if exist ".venv\Scripts\python.exe" goto :venv_ok
echo     Could not create the environment. See setup_log.txt.
echo STEP2_VENV_FAILED>> "%LOG%"
goto :fail
:venv_ok
set "VPY=%ROOT%\.venv\Scripts\python.exe"

echo [3/5] Installing packages. This takes 1-3 minutes...
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 goto :pip_fail

echo [4/5] Running the tests...
"%VPY%" -m pytest -q >> "%LOG%" 2>&1
if errorlevel 1 goto :test_fail
echo     All tests passed.

echo [5/5] Practice run with a fake model. Free, no API key needed...
if exist run_mock rmdir /s /q run_mock
"%VPY%" -m twins all --mock >> "%LOG%" 2>&1
if errorlevel 1 goto :demo_fail
start "" "%ROOT%\run_mock\results\index.html"

echo SETUP_OK>> "%LOG%"
echo.
echo ==== Setup complete ====
echo The practice report has opened in your browser. It has a red MOCK banner: its numbers are fake.
echo.
echo Next: double-click run_kill_test.bat to run the real experiment. It asks for your Anthropic API key.
echo.
pause
exit /b 0

:pip_fail
echo     Package install failed. Check your internet connection. Details in setup_log.txt.
echo STEP3_PIP_FAILED>> "%LOG%"
goto :fail
:test_fail
echo     Some tests failed. Details in setup_log.txt.
echo STEP4_TESTS_FAILED>> "%LOG%"
goto :fail
:demo_fail
echo     The practice run failed. Details in setup_log.txt.
echo STEP5_DEMO_FAILED>> "%LOG%"
goto :fail

:fail
echo.
echo ---- last lines of setup_log.txt ----
powershell -NoProfile -Command "Get-Content -Tail 25 '%LOG%'"
echo.
pause
exit /b 1

:try_cmd
%* "%ROOT%\tools\check_python.py" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 0
set "PY=%*"
exit /b 0

:try_path
if not exist "%~1" exit /b 0
"%~1" "%ROOT%\tools\check_python.py" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 0
set PY="%~1"
exit /b 0
