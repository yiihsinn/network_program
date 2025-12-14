#!/bin/bash

SERVER="linux2.cs.nycu.edu.tw"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

main_menu() {
    while true; do
        clear
        echo ""
        echo "========================================"
        echo "       HW3 Game Store System"
        echo "========================================"
        echo "  Server: $SERVER"
        echo "========================================"
        echo ""
        echo " 1. Player Client (玩家)"
        echo " 2. Developer Client (開發者)"
        echo " 3. Exit"
        echo ""
        read -p "Select: " choice

        case $choice in
            1) player_menu ;;
            2) developer_menu ;;
            3) echo "Goodbye!"; exit 0 ;;
            *) echo "Invalid choice."; sleep 2 ;;
        esac
    done
}

player_menu() {
    echo ""
    echo "Starting Player Client..."
    python3 "$SCRIPT_DIR/client/player_client.py" "$SERVER"
    echo ""
    read -p "Press Enter to continue..."
}

developer_menu() {
    while true; do
        clear
        echo ""
        echo "========================================"
        echo "       Developer Options"
        echo "========================================"
        echo ""
        echo " 1. Create New Game (建立新遊戲模板)"
        echo " 2. Login / Manage Games (登入管理)"
        echo " 3. Back"
        echo ""
        read -p "Select: " dev_choice

        case $dev_choice in
            1) create_template ;;
            2) dev_login ;;
            3) return ;;
            *) echo "Invalid choice."; sleep 2 ;;
        esac
    done
}

create_template() {
    echo ""
    echo "Starting Game Template Creator..."
    python3 "$SCRIPT_DIR/template/create_game_template.py"
    echo ""
    echo "Template created! You can now upload it via Developer Client."
    read -p "Press Enter to continue..."
}

dev_login() {
    echo ""
    echo "Starting Developer Client..."
    python3 "$SCRIPT_DIR/client/developer_client.py" "$SERVER"
    echo ""
    read -p "Press Enter to continue..."
}

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found in PATH"
    echo "Please install Python3 and add to PATH"
    exit 1
fi

main_menu
