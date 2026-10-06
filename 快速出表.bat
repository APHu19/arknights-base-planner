@echo off
chcp 65001 >nul
title Arknights Base Planner - Quick Solve
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py" )
if not defined PY ( echo [ERROR] Python not found & pause & exit /b 1 )

echo ============================================================
echo  Quick Solve  (output goes to planner\out\)
echo ============================================================
echo   1. LMD max            (gold net >= 0)
echo   2. Orundum            (shards >= orundum station demand)
echo   3. Burn gold stock    (gold consume)
echo   4. Burn shard stock   (shard consume)
echo   5. Hoard gold+shards  (produce both)
echo   6. EXP max
echo   7. Clue speed max     (meeting room)
echo   8. List all options
echo   0. Exit
echo ------------------------------------------------------------
set "ARG="
set /p CH=Enter number: 
if "%CH%"=="1" set ARG=--main lmd --gold no_deficit --shard none
if "%CH%"=="2" set ARG=--main yu --gold none --shard ge_trade
if "%CH%"=="3" set ARG=--main lmd --gold consume --shard none
if "%CH%"=="4" set ARG=--main yu --gold none --shard consume
if "%CH%"=="5" set ARG=--main balanced --gold produce --shard produce
if "%CH%"=="6" set ARG=--main exp --gold no_deficit --shard none
if "%CH%"=="7" set ARG=--main clue
if "%CH%"=="8" set ARG=--list
if "%CH%"=="0" exit /b 0
if not defined ARG ( echo Invalid input & pause & exit /b 1 )

"%PY%" "planner\cli.py" solve %ARG% --out "planner\out"
echo.
echo Done. Files are in planner\out\
pause
