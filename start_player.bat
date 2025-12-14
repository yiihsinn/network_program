@echo off
REM ========================================
REM  HW3 Game Store - Player Client Startup
REM ========================================
echo Starting Player Client...
cd /d %~dp0
python client/player_client.py %*
pause
