@echo off
setlocal
cd /d "%~dp0"
where docker >nul 2>&1
if errorlevel 1 (
  echo Docker was not found. Install and open Docker Desktop, then try again.
  pause
  exit /b 1
)
where py >nul 2>&1
if not errorlevel 1 (
  py -3 scripts\setup.py
) else (
  python scripts\setup.py
)
if errorlevel 1 (
  echo Setup failed. Check that Python 3.11 or newer is installed.
  pause
  exit /b 1
)
docker compose up --build
if errorlevel 1 (
  echo Startup failed. Check Docker Desktop is running and read docs\WINDOWS_SETUP.md.
  pause
  exit /b 1
)
