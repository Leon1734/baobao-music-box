@echo off
title Stop Baobao Music Box
echo Stopping Baobao Music Box server...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8082" ^| findstr "LISTENING"') do (
  echo Killing PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

ping -n 2 127.0.0.1 >nul
netstat -ano | findstr ":8082" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo [WARN] Port 8082 still in use
) else (
  echo [OK] Server stopped
)
ping -n 3 127.0.0.1 >nul
