#!/bin/bash
# HW3 Game Store - Stop All Servers
echo "Stopping all servers..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .server_pids ]; then
    read -r DB_PID DEV_PID LOBBY_PID < .server_pids
    kill $DB_PID $DEV_PID $LOBBY_PID 2>/dev/null
    rm .server_pids
    echo "Servers stopped."
else
    # Fallback: kill all python processes on our ports
    pkill -f "db_server.py" 2>/dev/null
    pkill -f "developer_server.py" 2>/dev/null
    pkill -f "lobby_server.py" 2>/dev/null
    echo "Attempted to stop servers."
fi
