@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem Puts the full project, with its commit history, into a fresh folder next to this one and pushes it to GitHub.
where git >nul 2>&1
if errorlevel 1 (
  echo Git isn't installed. Install it from https://git-scm.com/download/win with the default options,
  echo then double-click this file again.
  pause
  exit /b 1
)
if not exist "%~dp0profile-twins.bundle" (
  echo profile-twins.bundle is missing from this folder.
  pause
  exit /b 1
)
set "OUT=%~dp0..\under-pressure"
if exist "%OUT%\.git" goto :have_clone
git clone --branch main "%~dp0profile-twins.bundle" "%OUT%"
if errorlevel 1 goto :failed
:have_clone
echo.
echo Step 1. In your browser, open https://github.com/new
echo         Name it under-pressure, make it Public, and leave every "Add ..." box unticked.
echo Step 2. Copy the repository URL GitHub shows, e.g. https://github.com/TayyibI/under-pressure.git
echo.
set /p "URL=Paste the URL here and press Enter: "
if not defined URL goto :failed
cd /d "%OUT%"
git remote remove origin >nul 2>&1
git remote add origin "%URL%"
git push -u origin main
if errorlevel 1 goto :failed
echo.
echo Pushed. Last step, on GitHub: Settings, then Pages, then Source: GitHub Actions.
echo A minute later the page is live at https://YOUR-USERNAME.github.io/under-pressure/
echo.
pause
exit /b 0
:failed
echo.
echo Something went wrong. Copy what's above and send it to Claude.
pause
exit /b 1
