@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   HW3 資料重置腳本
echo ========================================
echo.
echo 此腳本將：
echo   1. 清空本地資料
echo   2. 上傳到遠端伺服器
echo   3. 重啟遠端伺服器
echo.
set /p confirm="確定要執行? (y/n): "

if /i not "%confirm%"=="y" (
    echo 取消操作
    pause
    exit /b
)

echo.
echo ========================================
echo   [1/3] 清空本地資料
echo ========================================

:: 重設資料庫
echo {"User": {}, "Developer": {}, "Room": {}, "Game": {}} > server\database.json
echo   [OK] database.json

:: 清空上架遊戲
if exist server\uploaded_games (
    rmdir /s /q server\uploaded_games
    echo   [OK] uploaded_games/
)

:: 清空玩家下載
if exist client\downloads (
    rmdir /s /q client\downloads
    echo   [OK] downloads/
)

:: 重設插件安裝
echo {} > client\plugins\installed.json
echo   [OK] installed.json

echo.
echo ========================================
echo   [2/3] 上傳到遠端伺服器
echo ========================================

set REMOTE_USER=yhlee0820
set REMOTE_HOST=linux2.cs.nycu.edu.tw
set REMOTE_PATH=~/hw3

echo 上傳 server/*.py ...
scp server\*.py %REMOTE_USER%@%REMOTE_HOST%:%REMOTE_PATH%/server/

echo 重設遠端資料庫...
scp server\database.json %REMOTE_USER%@%REMOTE_HOST%:%REMOTE_PATH%/server/

echo.
echo ========================================
echo   [3/3] 重啟遠端伺服器
echo ========================================
echo.
echo 請在遠端 SSH 執行以下指令重啟伺服器：
echo.
echo   pkill -f "python3 server/"
echo   cd ~/hw3
echo   nohup python3 server/db_server.py ^>^& db.log ^&
echo   nohup python3 server/developer_server.py ^>^& dev.log ^&
echo   nohup python3 server/lobby_server.py ^>^& lobby.log ^&
echo.
echo ========================================
echo   完成！
echo ========================================
echo.
pause
