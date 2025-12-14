#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "========================================"
echo "  HW3 資料重置腳本"
echo "========================================"
echo ""
echo "此腳本將清空以下資料："
echo "  - server/database.json (帳號/遊戲資料)"
echo "  - server/uploaded_games/ (上架遊戲)"
echo "  - client/downloads/ (玩家下載)"
echo "  - client/plugins/installed.json (已安裝插件)"
echo ""
read -p "確定要清空所有資料? (y/n): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "取消操作"
    exit 0
fi

echo ""
echo "正在清空資料..."

# 重設資料庫
echo '{"User": {}, "Developer": {}, "Room": {}, "Game": {}}' > "$SCRIPT_DIR/server/database.json"
echo "  [OK] database.json"

# 清空上架遊戲
if [ -d "$SCRIPT_DIR/server/uploaded_games" ]; then
    rm -rf "$SCRIPT_DIR/server/uploaded_games"
    echo "  [OK] uploaded_games/"
fi

# 清空玩家下載
if [ -d "$SCRIPT_DIR/client/downloads" ]; then
    rm -rf "$SCRIPT_DIR/client/downloads"
    echo "  [OK] downloads/"
fi

# 重設插件安裝
echo '{}' > "$SCRIPT_DIR/client/plugins/installed.json"
echo "  [OK] installed.json"

echo ""
echo "========================================"
echo "  資料已清空完成!"
echo "========================================"
echo ""
