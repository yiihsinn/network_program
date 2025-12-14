@echo off
REM ========================================
REM  HW3 Game Store - Developer Client Startup
REM ========================================
echo Starting Developer Client...
cd /d %~dp0
python client/developer_client.py %*
pause
