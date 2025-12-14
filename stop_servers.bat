@echo off
REM ========================================
REM  HW3 Game Store - Stop All Servers
REM ========================================
echo Stopping all Python processes...
taskkill /F /IM python.exe 2>nul
echo.
echo All servers stopped.
pause
