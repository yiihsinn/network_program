#!/bin/bash
# ========================================
#  HW3 Game Store - Server Startup Script
# ========================================
echo "Starting HW3 Game Store Servers..."
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Start Database Server
echo "[1/3] Starting Database Server (Port 10001)..."
python3 server/db_server.py &
DB_PID=$!
sleep 1

# Start Developer Server
echo "[2/3] Starting Developer Server (Port 10003)..."
python3 server/developer_server.py &
DEV_PID=$!
sleep 1

# Start Lobby Server
echo "[3/3] Starting Lobby Server (Port 10002)..."
python3 server/lobby_server.py &
LOBBY_PID=$!
sleep 1

echo
echo "========================================"
echo " All servers started!"
echo "========================================"
echo
echo "Server PIDs:"
echo "  - Database Server:  $DB_PID"
echo "  - Developer Server: $DEV_PID"
echo "  - Lobby Server:     $LOBBY_PID"
echo
echo "To stop all servers: ./stop_servers.sh"
echo "Or press Ctrl+C to kill all background processes"

# Save PIDs to file for stop script
echo "$DB_PID $DEV_PID $LOBBY_PID" > .server_pids

# Wait for user interrupt
wait
