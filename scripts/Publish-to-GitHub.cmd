@echo off
setlocal EnableExtensions
title AUTONOMUS - Publish to GitHub

rem ---------------------------------------------------------------
rem  Double-click launcher for scripts\publish_to_github.ps1
rem  Put this file next to publish_to_github.ps1 (e.g. in Downloads).
rem  Authentication is handled by Git Credential Manager / browser.
rem  This file contains no credentials.
rem ---------------------------------------------------------------

set "PS1=%~dp0publish_to_github.ps1"
if not exist "%PS1%" set "PS1=%USERPROFILE%\Devil-AI-OS\scripts\publish_to_github.ps1"

if not exist "%PS1%" (
    echo.
    echo  ERROR: publish_to_github.ps1 was not found.
    echo.
    echo  Put Publish-to-GitHub.cmd and publish_to_github.ps1 in the same
    echo  folder, or publish the package once so the repo copy exists at
    echo  %USERPROFILE%\Devil-AI-OS\scripts\
    echo.
    pause
    exit /b 1
)

where powershell >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Windows PowerShell was not found on PATH.
    echo.
    pause
    exit /b 1
)

:menu
cls
echo.
echo  ============================================================
echo    AUTONOMUS  -  Publish work to GitHub
echo  ============================================================
echo.
echo    Repository : github.com/itshamiz01/Devil-AI-OS
echo    Script     : %PS1%
echo.
echo    The newest AUTONOMUS_*.zip in Downloads, Desktop, this
echo    folder, or the repo folder is used automatically.
echo.
echo  ------------------------------------------------------------
echo    1   Preview only    (changes nothing)
echo    2   Publish now     (commit and push)
echo    3   Publish + tests (run backend tests first)
echo    4   Exit
echo  ------------------------------------------------------------
echo.

set "CHOICE="
set /p "CHOICE=  Choose 1-4 and press Enter: "

set "ARGS="
set "PREVIEW="

if "%CHOICE%"=="1" (
    set "ARGS=-DryRun"
    set "PREVIEW=1"
    goto run
)
if "%CHOICE%"=="2" goto run
if "%CHOICE%"=="3" (
    set "ARGS=-RunTests"
    goto run
)
if "%CHOICE%"=="4" exit /b 0

echo.
echo  Please enter 1, 2, 3 or 4.
timeout /t 2 >nul
goto menu

:run
echo.
echo  ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %ARGS%
set "RC=%ERRORLEVEL%"
echo.
echo  ============================================================
if "%RC%"=="0" (
    echo    Finished successfully.
) else (
    echo    STOPPED - exit code %RC%. Read the message above.
    echo    Nothing was forced. Your local work is still on disk.
)
echo  ============================================================
echo.
pause

if defined PREVIEW goto menu
exit /b %RC%
