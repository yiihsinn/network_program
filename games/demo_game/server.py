#!/usr/bin/env python3
import sys
import socket
import threading

def handle_client(conn, addr):
    print(f"Player {addr} connected")
    conn.send(b"Welcome to the game!\n")
    # TODO: Implement game logic here

def main():
    if len(sys.argv) < 3:
        print("Usage: python server.py <port> <num_players>")
        return

    port = int(sys.argv[1])
    num_players = int(sys.argv[2])

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', port))
    s.listen(num_players)
    
    print(f"Game Server listening on {port} for {num_players} players...")
    
    clients = []
    while len(clients) < num_players:
        conn, addr = s.accept()
        clients.append(conn)
        threading.Thread(target=handle_client, args=(conn, addr)).start()
    
    # TODO: Game Loop...

if __name__ == "__main__":
    main()