#!/usr/bin/env python3
"""
MultiClick Server - Level C (GUI 2-4 Players)
15 second clicking competition with lobby phase
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
    except:
        return None

class MultiClickServer:
    def __init__(self, port, max_players):
        self.port = port
        self.max_players = max(2, min(4, max_players))  # 2-4 players
        self.min_players = 2  # Min to start
        self.players = []
        self.player_names = []
        self.clicks = []
        self.game_duration = 15  # seconds
        self.game_running = False
        self.lobby_phase = True
        self.host_ready = False
        self.lock = threading.Lock()
    
    def broadcast(self, data):
        for sock in self.players:
            try:
                send_json(sock, data)
            except:
                pass
    
    def broadcast_player_list(self):
        """Send current player list to all connected players"""
        player_info = []
        for i, name in enumerate(self.player_names):
            player_info.append({
                "name": name,
                "is_host": i == 0,
                "player_id": i + 1
            })
        self.broadcast({
            "type": "player_list",
            "players": player_info,
            "current": len(self.players),
            "max": self.max_players,
            "min_required": self.min_players
        })
    
    def handle_player(self, player_idx, sock):
        """Handle clicks from a player during game"""
        sock.settimeout(1.0)
        while self.game_running:
            try:
                msg = recv_json(sock)
                if msg and msg.get('type') == 'click':
                    with self.lock:
                        if player_idx < len(self.clicks):
                            self.clicks[player_idx] += 1
            except socket.timeout:
                continue
            except:
                break
    
    def handle_lobby(self, player_idx, sock):
        """Handle lobby messages from a player"""
        sock.settimeout(1.0)
        while self.lobby_phase:
            try:
                msg = recv_json(sock)
                if not msg:
                    continue
                    
                msg_type = msg.get('type')
                
                # Host can start the game
                if msg_type == 'start_game' and player_idx == 0:
                    if len(self.players) >= self.min_players:
                        self.host_ready = True
                        return
                    else:
                        send_json(sock, {"type": "error", "message": f"需要至少 {self.min_players} 位玩家才能開始"})
                
                elif msg_type == 'leave':
                    return
                    
            except socket.timeout:
                continue
            except:
                break
    
    def get_rankings(self):
        """Return sorted list of (player_name, score) tuples"""
        with self.lock:
            scores = [(self.player_names[i], self.clicks[i]) for i in range(len(self.players))]
        return sorted(scores, key=lambda x: -x[1])
    
    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', self.port))
        server.listen(self.max_players)
        
        print(f"[MultiClick] Listening on port {self.port} for up to {self.max_players} players...")
        
        # LOBBY PHASE - wait until host clicks Start
        lobby_threads = []
        try:
            while self.lobby_phase and not self.host_ready:
                try:
                    # Only accept new players if not at max
                    if len(self.players) < self.max_players:
                        server.settimeout(1.0)
                        try:
                            conn, addr = server.accept()
                            
                            # Receive name from client
                            conn.settimeout(5.0)
                            join_msg = recv_json(conn)
                            if join_msg and join_msg.get('type') == 'join':
                                name = join_msg.get('name', f"Player{len(self.players) + 1}")
                            else:
                                name = f"Player{len(self.players) + 1}"
                            
                            player_id = len(self.players)
                            self.players.append(conn)
                            self.clicks.append(0)
                            self.player_names.append(name)
                            
                            is_host = (player_id == 0)
                            print(f"[MultiClick] {name} connected from {addr} {'(Host)' if is_host else ''}")
                            
                            send_json(conn, {
                                "type": "welcome",
                                "player_id": player_id + 1,
                                "your_name": name,
                                "is_host": is_host,
                                "max_players": self.max_players,
                                "min_players": self.min_players,
                                "message": "你是房主！" if is_host else "等待房主開始遊戲..."
                            })
                            
                            self.broadcast_player_list()
                            
                            t = threading.Thread(target=self.handle_lobby, args=(player_id, conn))
                            t.start()
                            lobby_threads.append(t)
                        except socket.timeout:
                            pass  # No new connection, continue checking host_ready
                    else:
                        # At max players, just wait for host
                        time.sleep(0.5)
                        
                except Exception as e:
                    print(f"[MultiClick] Lobby loop error: {e}")
                    break
                    
        except Exception as e:
            print(f"[MultiClick] Lobby error: {e}")
        
        if len(self.players) < self.min_players:
            print("[MultiClick] Not enough players")
            self.broadcast({"type": "error", "message": "玩家不足，遊戲取消"})
            for p in self.players:
                p.close()
            server.close()
            return
        
        self.lobby_phase = False
        for t in lobby_threads:
            t.join(timeout=1)
        
        # COUNTDOWN
        for count in [3, 2, 1]:
            self.broadcast({"type": "countdown", "count": count})
            time.sleep(1)
        
        # GAME PHASE
        self.game_running = True
        self.broadcast({
            "type": "game_start", 
            "duration": self.game_duration,
            "players": self.player_names
        })
        
        threads = []
        for i, sock in enumerate(self.players):
            t = threading.Thread(target=self.handle_player, args=(i, sock))
            t.start()
            threads.append(t)
        
        # Game loop with updates
        start_time = time.time()
        last_update = 0
        while time.time() - start_time < self.game_duration:
            elapsed = time.time() - start_time
            remaining = self.game_duration - elapsed
            
            if elapsed - last_update >= 0.3:
                rankings = self.get_rankings()
                self.broadcast({
                    "type": "update",
                    "remaining": round(remaining, 1),
                    "rankings": [{"name": name, "score": score} for name, score in rankings]
                })
                last_update = elapsed
            
            time.sleep(0.05)
        
        self.game_running = False
        for t in threads:
            t.join(timeout=2)
        
        # Final rankings
        rankings = self.get_rankings()
        winner = rankings[0][0] if rankings else "No winner"
        
        for i, sock in enumerate(self.players):
            my_name = self.player_names[i]
            my_rank = next((idx+1 for idx, (name, _) in enumerate(rankings) if name == my_name), 0)
            
            if my_rank == 1:
                result = "🥇 第一名！你贏了！"
            elif my_rank == 2:
                result = "🥈 第二名！"
            elif my_rank == 3:
                result = "🥉 第三名！"
            else:
                result = f"第 {my_rank} 名"
            
            send_json(sock, {
                "type": "game_over",
                "your_rank": my_rank,
                "your_result": result,
                "your_score": self.clicks[i],
                "rankings": [{"name": name, "score": score, "rank": idx+1} for idx, (name, score) in enumerate(rankings)],
                "winner": winner
            })
        
        time.sleep(3)
        for p in self.players:
            p.close()
        server.close()
        print("[MultiClick] Game ended")

def main():
    if len(sys.argv) < 3:
        print("Usage: python server.py <port> <max_players>")
        return

    port = int(sys.argv[1])
    max_players = int(sys.argv[2])
    
    if max_players < 2:
        max_players = 2
    if max_players > 4:
        max_players = 4
    
    server = MultiClickServer(port, max_players)
    server.run()

if __name__ == "__main__":
    main()
