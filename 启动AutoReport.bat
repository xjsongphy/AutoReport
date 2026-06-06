@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"

set "LOGFILE=%~dp0startup.log"
echo AutoReport Startup Log - %date% %time%> "%LOGFILE%"

echo ======================================
echo    AutoReport - Physics Experiment
echo    Report Generation System
echo ======================================
echo.
echo Startup log: startup.log
echo.

REM Find uv
set "UV="
where uv >nul 2>&1
if !errorlevel! equ 0 (
    set "UV=uv"
    goto :found
)

if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "UV=%USERPROFILE%\.local\bin\uv.exe"
    goto :found
)
if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
    set "UV=%USERPROFILE%\.cargo\bin\uv.exe"
    goto :found
)
if exist "%LOCALAPPDATA%\uv\uv.exe" (
    set "UV=%LOCALAPPDATA%\uv\uv.exe"
    goto :found
)

echo [ERROR] uv not found. >> "%LOGFILE%"
echo [ERROR] uv package manager not found.
echo Please install: https://docs.astral.sh/uv/
echo.
echo Install command:
echo   powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
echo.
pause
exit /b 1

:found
echo uv path: !UV!>> "%LOGFILE%"
echo Starting...>> "%LOGFILE%"
echo Starting AutoReport...
echo.

"!UV!" run autoreport >> "%LOGFILE%" 2>&1

echo Exit code: !errorlevel!>> "%LOGFILE%"
echo End time: %date% %time%>> "%LOGFILE%"

if !errorlevel! neq 0 (
    echo.
    echo ======================================
    echo STARTUP FAILED (code: !errorlevel!)
    echo Please check startup.log for details
    echo ======================================
)
pause
