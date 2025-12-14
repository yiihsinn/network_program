#!/usr/bin/env python3
"""
RockPaperScissors Server - Level A (CLI 2-Player)
3 rounds, best of 3 wins
"""
import sys
import socket
import json
import threading
import time

def send_json(sock, data):
    """Send JSON message with length prefix"""
    msg = json.dumps(data).encode()
    length = len(msg).to_bytes(4, 'big')
    try:
        sock.sendall(length + msg)
        return True
    except:
        return False

def recv_json(sock):
    """Receive JSON message with length prefix"""
    try:
        length_data = sock.recv(4)
        if not length_data:
            return None
        length = int.from_bytes(length_data, 'big')
        if length > 10000:
            return None
        data = b''
        while len(data) < length:
            chunk = sock.recv(min(4096, length - len(data)))
            if not chunk:
                return None
            data += chunk
        return json.loads(data.decode())
    except socket.timeout:
        return None
    except:
        return None

def determine_winner(choice1, choice2):
    """Return: 1 if player1 wins, 2 if player2 wins, 0 if tie"""
    if choice1 == choice2:
        return 0
    wins = {'R': 'S', 'P': 'R', 'S': 'P'}  # R beats S, etc.
    return 1 if wins.get(choice1) == choice2 else 2

def main():
    if len(sys.argv) < 3:
        print("Usage: python server.py <port> <num_players>")
        return

    port = int(sys.argv[1])
    num_players = int(sys.argv[2])
    
    if num_players != 2:
        print("This game requires exactly 2 players")
        return

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(2)
    server.settimeout(60)
    
    print(f"[RPS Server] Listening on port {port}...")
    
    players = []
    try:
        for i in range(2):
            conn, addr = server.accept()
            conn.settimeout(120)  # Long timeout for player input
            players.append(conn)
            print(f"[RPS Server] Player {i+1} connected from {addr}")
            send_json(conn, {"type": "welcome", "player_id": i+1, "message": "等待另一位玩家..."})
    except socket.timeout:
        print("[RPS Server] Timeout waiting for players")
        for p in players:
            p.close()
        server.close()
        return
    
    # Notify both players game is starting
    for i, p in enumerate(players):
        send_json(p, {"type": "game_start", "message": "遊戲開始！剪刀石頭布！", "you_are": f"Player {i+1}"})
    
    scores = [0, 0]  # Player 1, Player 2
    
    # Play 3 rounds (or until someone wins 2)
    for round_num in range(1, 4):
        if scores[0] >= 2 or scores[1] >= 2:
            break
            
        print(f"[RPS Server] Round {round_num}")
        
        # Send round start
        for p in players:
            send_json(p, {"type": "round_start", "round": round_num, "scores": scores})
        
        # Collect choices - WAIT FOR BOTH PLAYERS
        choices = [None, None]
        lock = threading.Lock()
        
        def get_choice(player_idx):
            """Get choice from one player - blocks until received"""
            try:
                msg = recv_json(players[player_idx])
                if msg and msg.get('type') == 'choice':
                    choice = msg.get('value', '').upper()
                    if choice in ('R', 'P', 'S'):
                        with lock:
                            choices[player_idx] = choice
                        print(f"[RPS Server] Player {player_idx+1} chose: {choice}")
            except Exception as e:
                print(f"[RPS Server] Error getting choice from player {player_idx+1}: {e}")
        
        # Start threads for each player
        threads = [threading.Thread(target=get_choice, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        
        # Wait for BOTH threads to complete (no timeout - wait as long as needed)
        for t in threads:
            t.join()  # No timeout - wait until both players respond
        
        print(f"[RPS Server] Choices received: {choices}")
        
        # If someone disconnected, default to R
        for i in range(2):
            if choices[i] is None:
                print(f"[RPS Server] Player {i+1} disconnected, using default R")
                choices[i] = 'R'
        
        # Determine winner
        winner = determine_winner(choices[0], choices[1])
        if winner == 1:
            scores[0] += 1
        elif winner == 2:
            scores[1] += 1
        
        print(f"[RPS Server] Round {round_num} result: P1={choices[0]}, P2={choices[1]}, winner={winner}")
        
        # Send results
        choice_names = {'R': '石頭', 'P': '布', 'S': '剪刀'}
        for i, p in enumerate(players):
            opponent_idx = 1 - i
            result = "平手"
            if winner == i + 1:
                result = "你贏了！"
            elif winner != 0:
                result = "你輸了"
            
            send_json(p, {
                "type": "round_result",
                "round": round_num,
                "your_choice": choice_names.get(choices[i], choices[i]),
                "opponent_choice": choice_names.get(choices[opponent_idx], choices[opponent_idx]),
                "result": result,
                "scores": scores
            })
        
        time.sleep(1)  # Brief pause between rounds
    
    # Game over
    final_winner = "平手"
    if scores[0] > scores[1]:
        final_winner = "Player 1"
    elif scores[1] > scores[0]:
        final_winner = "Player 2"
    
    for i, p in enumerate(players):
        your_result = "你贏了！🎉" if (i == 0 and scores[0] > scores[1]) or (i == 1 and scores[1] > scores[0]) else "你輸了 😢"
        if scores[0] == scores[1]:
            your_result = "平手！"
        send_json(p, {
            "type": "game_over",
            "your_result": your_result,
            "final_scores": f"{scores[0]} - {scores[1]}",
            "winner": final_winner
        })
    
    time.sleep(1)
    for p in players:
        p.close()
    server.close()
    print("[RPS Server] Game ended")

if __name__ == "__main__":
    main()
