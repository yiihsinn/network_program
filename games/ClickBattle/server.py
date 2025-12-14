#!/usr/bin/env python3
"""
ClickBattle Server - Level B (GUI 2-Player)
10 second clicking competition with lobby phase
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

class ClickBattleServer:
    def __init__(self, port, num_players=2):
        self.port = port
        self.num_players = num_players
        self.players = []
        self.player_names = []
        self.clicks = []
        self.game_duration = 10  # seconds
        self.game_running = False
        self.lobby_phase = True
        self.host_ready = False
        self.lock = threading.Lock()
    
    def broadcast(self, data, exclude=None):
        for i, sock in enumerate(self.players):
            if sock != exclude:
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
            "required": self.num_players
        })
    
    def handle_player(self, player_idx, sock):
        """Handle clicks from a player during game"""
        sock.settimeout(1.0)
        while self.game_running:
            try:
                msg = recv_json(sock)
                if msg and msg.get('type') == 'click':
                    with self.lock:
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
                if msg_type == 'start_game' and player_idx == 0:  # Only host
                    if len(self.players) >= 2:
                        self.host_ready = True
                        return
                    else:
                        send_json(sock, {"type": "error", "message": "需要 2 位玩家才能開始"})
                
                # Player can leave
                elif msg_type == 'leave':
                    return
                    
            except socket.timeout:
                continue
            except:
                break
    
    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', self.port))
        server.listen(self.num_players)
        server.settimeout(300)  # 5 minute timeout for lobby
        
        print(f"[ClickBattle] Listening on port {self.port}...")
        
        # LOBBY PHASE: Wait until host clicks Start
        lobby_threads = []
        try:
            while self.lobby_phase and not self.host_ready:
                try:
                    # Only accept new players if not at max
                    if len(self.players) < self.num_players:
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
                            print(f"[ClickBattle] {name} connected from {addr} {'(Host)' if is_host else ''}")
                            
                            # Send welcome
                            send_json(conn, {
                                "type": "welcome",
                                "player_id": player_id + 1,
                                "your_name": name,
                                "is_host": is_host,
                                "message": "等待其他玩家加入..." if not is_host else "你是房主！等待玩家加入後點擊開始"
                            })
                            
                            # Update all players
                            self.broadcast_player_list()
                            
                            # Start lobby handler thread
                            t = threading.Thread(target=self.handle_lobby, args=(player_id, conn))
                            t.start()
                            lobby_threads.append(t)
                        except socket.timeout:
                            pass  # No new connection
                    else:
                        # All players connected, just wait for host
                        time.sleep(0.5)
                        
                except Exception as e:
                    print(f"[ClickBattle] Lobby loop error: {e}")
                    break
                    
        except Exception as e:
            print(f"[ClickBattle] Lobby error: {e}")
        
        # Check if we have enough players
        if len(self.players) < 2:
            print("[ClickBattle] Not enough players, shutting down")
            self.broadcast({"type": "error", "message": "玩家不足，遊戲取消"})
            for p in self.players:
                p.close()
            server.close()
            return
        
        self.lobby_phase = False
        
        # Stop lobby threads
        for t in lobby_threads:
            t.join(timeout=1)
        
        # COUNTDOWN
        for count in [3, 2, 1]:
            self.broadcast({"type": "countdown", "count": count})
            time.sleep(1)
        
        # GAME PHASE
        self.game_running = True
        self.broadcast({"type": "game_start", "duration": self.game_duration})
        
        # Start player threads
        threads = []
        for i, sock in enumerate(self.players):
            t = threading.Thread(target=self.handle_player, args=(i, sock))
            t.start()
            threads.append(t)
        
        # Game timer with updates
        start_time = time.time()
        last_update = 0
        while time.time() - start_time < self.game_duration:
            elapsed = time.time() - start_time
            remaining = self.game_duration - elapsed
            
            if elapsed - last_update >= 0.3:
                with self.lock:
                    for i, sock in enumerate(self.players):
                        opponent_idx = 1 - i
                        send_json(sock, {
                            "type": "update",
                            "remaining": round(remaining, 1),
                            "you": self.clicks[i],
                            "your_name": self.player_names[i],
                            "opponent": self.clicks[opponent_idx],
                            "opponent_name": self.player_names[opponent_idx]
                        })
                last_update = elapsed
            
            time.sleep(0.05)
        
        self.game_running = False
        
        for t in threads:
            t.join(timeout=2)
        
        # Determine winner
        with self.lock:
            if self.clicks[0] > self.clicks[1]:
                winner = self.player_names[0]
            elif self.clicks[1] > self.clicks[0]:
                winner = self.player_names[1]
            else:
                winner = "平手"
        
        # Send results
        for i, sock in enumerate(self.players):
            opponent_idx = 1 - i
            if self.clicks[i] > self.clicks[opponent_idx]:
                result = "你贏了！🎉"
            elif self.clicks[i] < self.clicks[opponent_idx]:
                result = "你輸了 😢"
            else:
                result = "平手！"
            
            send_json(sock, {
                "type": "game_over",
                "your_clicks": self.clicks[i],
                "opponent_clicks": self.clicks[opponent_idx],
                "your_result": result,
                "winner": winner
            })
        
        time.sleep(2)
        for p in self.players:
            p.close()
        server.close()
        print("[ClickBattle] Game ended")

def main():
    if len(sys.argv) < 3:
        print("Usage: python server.py <port> <num_players>")
        return

    port = int(sys.argv[1])
    num_players = int(sys.argv[2])
    
    if num_players != 2:
        print("This game requires exactly 2 players")
        return
    
    server = ClickBattleServer(port, num_players)
    server.run()

if __name__ == "__main__":
    main()
