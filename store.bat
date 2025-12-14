@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
title HW3 Game Store

:: Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH
    echo Please install Python and add to PATH
    pause
    exit /b 1
)

set SERVER=linux2.cs.nycu.edu.tw
cd /d "%~dp0"

:main
cls
echo.
echo ========================================
echo        HW3 Game Store System
echo ========================================
echo   Server: %SERVER%
echo ========================================
echo.
echo  1. Player Client (玩家)
echo  2. Developer Client (開發者)
echo  3. Exit
echo.
set /p choice="Select: "

if "%choice%"=="1" goto player
if "%choice%"=="2" goto developer
if "%choice%"=="3" goto end

echo Invalid choice.
timeout /t 2 >nul
goto main

:player
echo.
echo Starting Player Client...
python "%~dp0client\player_client.py" %SERVER%
echo.
pause
goto main

:developer
cls
echo.
echo ========================================
echo        Developer Options
echo ========================================
echo.
echo  1. Create New Game (建立新遊戲模板)
echo  2. Login / Manage Games (登入管理)
echo  3. Back
echo.
set /p dev_choice="Select: "

if "%dev_choice%"=="1" goto create_template
if "%dev_choice%"=="2" goto dev_login
if "%dev_choice%"=="3" goto main

echo Invalid choice.
timeout /t 2 >nul
goto developer

:create_template
echo.
echo Starting Game Template Creator...
python "%~dp0template\create_game_template.py"
echo.
echo Template created! You can now upload it via Developer Client.
pause
goto developer

:dev_login
echo.
echo Starting Developer Client...
python "%~dp0client\developer_client.py" %SERVER%
echo.
pause
goto main

:end
echo Goodbye!
endlocal
exit /b 0
