@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title 预览最新版 - 宝宝音乐盒

echo ============================================
echo   预览最新版（直接跑源码，不是那个旧 exe）
echo ============================================
echo.

REM 先清掉占着 8082 的进程（旧 exe 或上次没退干净的实例）
REM 注意：按端口精确查，避免误杀别的项目进程
powershell -NoProfile -Command ^
  "$p=(Get-NetTCPConnection -LocalPort 8082 -State Listen -ErrorAction SilentlyContinue).OwningProcess;" ^
  "if($p){ Stop-Process -Id $p -Force; Write-Host ('  已关闭占用 8082 的进程 PID ' + $p) } else { Write-Host '  8082 空闲' }"
timeout /t 2 /nobreak >nul

REM 找 Python：优先系统里那个能装包的 3.13
set PY=
if exist "D:\Programs\Python313\python.exe" set PY=D:\Programs\Python313\python.exe
if not defined PY (
  for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PY set PY=%%i
  )
)
if not defined PY (
  echo [!] 找不到 Python，请手动确认安装路径
  pause
  exit /b 1
)
echo   使用 Python: %PY%
echo.
echo   正在启动（首次约 15 秒）...
echo   启动后会自动弹出窗口，关掉窗口即退出。
echo.

"%PY%" -u app.py

echo.
echo 已退出。
pause
