@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   HW3 資料重置腳本
echo ========================================
echo.
echo 此腳本將清空以下資料：
echo   - server/database.json (帳號/遊戲資料)
echo   - server/uploaded_games/ (上架遊戲)
echo   - client/downloads/ (玩家下載)
echo   - client/plugins/installed.json (已安裝插件)
echo.
set /p confirm="確定要清空所有資料? (y/n): "

if /i not "%confirm%"=="y" (
    echo 取消操作
    pause
    exit /b
)

echo.
echo 正在清空資料...

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
echo   資料已清空完成!
echo ========================================
echo.
pause
