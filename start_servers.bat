@echo off
REM ========================================
REM  HW3 Game Store - Server Startup Script
REM ========================================
echo Starting HW3 Game Store Servers...
echo.

REM Kill any existing Python processes on our ports (optional, comment out if not needed)
REM taskkill /F /IM python.exe 2>nul

REM Start Database Server
echo [1/3] Starting Database Server (Port 10001)...
start "DB Server" cmd /k "cd /d %~dp0 && python server/db_server.py"
timeout /t 2 /nobreak >nul

REM Start Developer Server
echo [2/3] Starting Developer Server (Port 10003)...
start "Developer Server" cmd /k "cd /d %~dp0 && python server/developer_server.py"
timeout /t 1 /nobreak >nul

REM Start Lobby Server
echo [3/3] Starting Lobby Server (Port 10002)...
start "Lobby Server" cmd /k "cd /d %~dp0 && python server/lobby_server.py"
timeout /t 1 /nobreak >nul

echo.
echo ========================================
echo  All servers started!
echo ========================================
echo.
echo Servers running in separate windows:
echo   - Database Server:  Port 10001
echo   - Developer Server: Port 10003
echo   - Lobby Server:     Port 10002
echo.
echo To stop all servers, close the windows or run: taskkill /F /IM python.exe
echo.
pause
