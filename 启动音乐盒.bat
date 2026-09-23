@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Baobao Music Box

echo ============================================
echo    Baobao Music Box - Starting
echo ============================================
echo.

REM ---- Find Python (python is often NOT in Windows PATH) ----
set PYEXE=
for %%P in (
  "D:\Programs\Python313\python.exe"
  "C:\Python313\python.exe"
  "C:\Python312\python.exe"
  "C:\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) do (
  if exist %%P if "!PYEXE!"=="" set PYEXE=%%~P
)

if "!PYEXE!"=="" (
  for /f "delims=" %%i in ('where python 2^>nul') do (
    if "!PYEXE!"=="" set PYEXE=%%i
  )
)

if "!PYEXE!"=="" (
  echo [ERROR] Python not found
  echo.
  echo Install Python 3.8+ from https://www.python.org/downloads/
  echo or edit this .bat and set PYEXE manually.
  echo.
  pause
  exit /b 1
)

echo [OK] Python: !PYEXE!
echo.

REM ---- Already running? ----
netstat -ano | findstr ":8082" | findstr "LISTENING" >nul 2>&1
if !errorlevel!==0 (
  echo [INFO] Server already running
  start "" "http://localhost:8082/player.html"
  ping -n 4 127.0.0.1 >nul
  exit /b 0
)

REM ---- Start server ----
echo [1/2] Starting server...
start "BaobaoMusicServer" /min cmd /c ""!PYEXE!" -u server.py > server.log 2>&1"

echo [2/2] Waiting for server...
set READY=0
for /l %%i in (1,1,20) do (
  if !READY!==0 (
    ping -n 2 127.0.0.1 >nul
    netstat -ano | findstr ":8082" | findstr "LISTENING" >nul 2>&1
    if !errorlevel!==0 set READY=1
  )
)

if !READY!==1 (
  echo [OK] Server ready
  start "" "http://localhost:8082/player.html"
  echo.
  echo ============================================
  echo   http://localhost:8082/player.html
  echo ============================================
  echo   Closing this window keeps the server alive.
  echo   To stop: close "BaobaoMusicServer" task.
  echo ============================================
  ping -n 6 127.0.0.1 >nul
) else (
  echo [ERROR] Server did not start within 20s
  echo.
  echo ---- server.log (last 20 lines) ----
  if exist server.log (
    powershell -NoProfile -Command "Get-Content server.log -Tail 20"
  ) else (
    echo   server.log not found
  )
  echo -------------------------------------
  echo.
  echo Run manually to see the error:
  echo   "!PYEXE!" server.py
  echo.
  pause
)
endlocal
