@echo off
chcp 65001 >nul
title Arknights Base Planner
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py" )
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.8+ and check "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Starting GUI ... (close the window to exit)
"%PY%" "planner\gui\app.py" %*
if errorlevel 1 (
  echo.
  echo [FAILED] see the error above. Common cause: Python not on PATH.
)

rem NOTE: no "pause" here, so automated calls like --selftest do not block.
