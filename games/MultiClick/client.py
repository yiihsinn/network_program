#!/usr/bin/env python3
"""
MultiClick Client - Level C (GUI 2-4 Players)
Tkinter GUI for multi-player clicking competition with lobby
"""
import sys
import socket
import json
import threading
import tkinter as tk
from tkinter import messagebox

def send_json(sock, data):
    msg = json.dumps(data).encode()
    length = len(msg).to_bytes(4, 'big')
    try:
        sock.sendall(length + msg)
        return True
    except:
        return False

def recv_json(sock):
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

class MultiClickClient:
    def __init__(self, server_ip, server_port, player_name="Player"):
        self.server_ip = server_ip
        self.server_port = server_port
        self.player_name = player_name
        self.sock = None
        self.running = True
        self.game_started = False
        self.is_host = False
        self.my_name = player_name
        self.min_players = 2
        
        # Create GUI
        self.root = tk.Tk()
        self.root.title("多人點擊大戰 - MultiClick")
        self.root.geometry("500x550")
        self.root.configure(bg='#1a1a2e')
        
        # Header
        self.title_label = tk.Label(
            self.root,
            text="🎮 多人點擊大戰",
            font=('Arial', 22, 'bold'),
            bg='#1a1a2e',
            fg='#e94560'
        )
        self.title_label.pack(pady=10)
        
        # Status
        self.status_label = tk.Label(
            self.root, 
            text="連線中...",
            font=('Arial', 14),
            bg='#1a1a2e',
            fg='white'
        )
        self.status_label.pack(pady=5)
        
        # Timer
        self.timer_label = tk.Label(
            self.root,
            text="",
            font=('Arial', 28, 'bold'),
            bg='#1a1a2e',
            fg='#e94560'
        )
        self.timer_label.pack(pady=5)
        
        # === LOBBY FRAME ===
        self.lobby_frame = tk.Frame(self.root, bg='#1a1a2e')
        self.lobby_frame.pack(pady=10, fill='x', padx=30)
        
        tk.Label(
            self.lobby_frame, 
            text="👥 玩家列表",
            font=('Arial', 16, 'bold'),
            bg='#1a1a2e',
            fg='white'
        ).pack()
        
        self.player_labels = []
        for i in range(4):  # Max 4 players
            label = tk.Label(
                self.lobby_frame,
                text="⚪ 等待中...",
                font=('Arial', 13),
                bg='#1a1a2e',
                fg='gray'
            )
            label.pack(pady=2)
            self.player_labels.append(label)
        
        # Start button (host only)
        self.start_button = tk.Button(
            self.lobby_frame,
            text="🚀 開始遊戲",
            font=('Arial', 16, 'bold'),
            width=15,
            height=2,
            bg='#e94560',
            fg='white',
            activebackground='#ff6b6b',
            command=self.on_start_game,
            state='disabled'
        )
        self.start_button.pack(pady=15)
        
        self.start_hint = tk.Label(
            self.lobby_frame,
            text="",
            font=('Arial', 11),
            bg='#1a1a2e',
            fg='#bdc3c7'
        )
        self.start_hint.pack()
        
        # === GAME FRAME ===
        self.game_frame = tk.Frame(self.root, bg='#1a1a2e')
        
        # Click button
        self.click_button = tk.Button(
            self.game_frame,
            text="點我！\n0",
            font=('Arial', 18, 'bold'),
            width=12,
            height=3,
            bg='#0f3460',
            fg='white',
            activebackground='#16213e',
            command=self.on_click,
            state='disabled'
        )
        self.click_button.pack(pady=10)
        
        # Leaderboard
        tk.Label(
            self.game_frame, 
            text="🏆 排行榜",
            font=('Arial', 16, 'bold'),
            bg='#1a1a2e',
            fg='#e94560'
        ).pack(pady=5)
        
        self.leaderboard_labels = []
        for i in range(4):
            label = tk.Label(
                self.game_frame,
                text="",
                font=('Arial', 14),
                bg='#1a1a2e',
                fg='white'
            )
            label.pack()
            self.leaderboard_labels.append(label)
        
        self.my_clicks = 0
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def on_start_game(self):
        if self.sock and self.is_host:
            send_json(self.sock, {"type": "start_game"})
            self.start_button.config(state='disabled', text="開始中...")
    
    def on_click(self):
        if self.sock and self.game_started:
            send_json(self.sock, {"type": "click"})
            self.my_clicks += 1
            self.root.after(0, lambda: self.click_button.config(text=f"點我！\n{self.my_clicks}"))
    
    def on_close(self):
        self.running = False
        if self.sock:
            try:
                send_json(self.sock, {"type": "leave"})
                self.sock.close()
            except:
                pass
        self.root.destroy()
    
    def update_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))
    
    def update_timer(self, text):
        self.root.after(0, lambda: self.timer_label.config(text=text))
    
    def update_player_list(self, players, current, max_players, min_required):
        def do_update():
            for i, label in enumerate(self.player_labels):
                if i < len(players):
                    p = players[i]
                    name = p.get('name', f'Player{i+1}')
                    is_host = p.get('is_host', False)
                    icon = "👑" if is_host else "🔵"
                    host_text = " (房主)" if is_host else ""
                    label.config(text=f"{icon} {name}{host_text}", fg='#4ecca3')
                elif i < max_players:
                    label.config(text="⚪ 等待中...", fg='gray')
                else:
                    label.config(text="")
            
            if self.is_host:
                if current >= min_required:
                    self.start_button.config(state='normal')
                    self.start_hint.config(text=f"可以開始！ ({current}/{max_players}人)", fg='#4ecca3')
                else:
                    self.start_button.config(state='disabled')
                    self.start_hint.config(text=f"需要至少 {min_required} 人 ({current}/{max_players})", fg='#bdc3c7')
            else:
                self.start_hint.config(text="等待房主開始遊戲...", fg='#bdc3c7')
        
        self.root.after(0, do_update)
    
    def switch_to_game(self):
        def do_switch():
            self.lobby_frame.pack_forget()
            self.game_frame.pack(pady=10, fill='both', expand=True)
            self.click_button.config(state='normal', bg='#e94560')
        self.root.after(0, do_switch)
    
    def update_leaderboard(self, rankings):
        def do_update():
            for i, label in enumerate(self.leaderboard_labels):
                if i < len(rankings):
                    r = rankings[i]
                    name = r.get('name', '???')
                    score = r.get('score', 0)
                    rank_icons = ['🥇', '🥈', '🥉', '4️⃣']
                    icon = rank_icons[i] if i < 4 else str(i+1)
                    
                    if name == self.my_name:
                        label.config(text=f"{icon} {name}: {score} ⬅️", fg='#e94560')
                    else:
                        label.config(text=f"{icon} {name}: {score}", fg='white')
                else:
                    label.config(text="")
        self.root.after(0, do_update)
    
    def show_result(self, result, rankings):
        def show():
            self.click_button.config(state='disabled', text=result)
            self.timer_label.config(text="遊戲結束!")
            
            ranking_text = "\n".join([
                f"{'🥇🥈🥉'[r.get('rank',1)-1] if r.get('rank',1)<=3 else str(r.get('rank'))+'. '} {r.get('name')}: {r.get('score')}"
                for r in rankings
            ])
            messagebox.showinfo("遊戲結束", f"{result}\n\n{ranking_text}")
            self.root.after(2000, self.on_close)
        self.root.after(0, show)
    
    def network_thread(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(120)
            self.sock.connect((self.server_ip, self.server_port))
            self.sock.settimeout(5)
            
            # Send player name on connect
            send_json(self.sock, {"type": "join", "name": self.player_name})
            
            self.update_status("已連線，等待其他玩家...")
            
            while self.running:
                try:
                    msg = recv_json(self.sock)
                    if not msg:
                        if self.running:
                            self.update_status("連線中斷")
                        break
                    
                    msg_type = msg.get('type')
                    
                    if msg_type == 'welcome':
                        self.my_name = msg.get('your_name', 'Player')
                        self.is_host = msg.get('is_host', False)
                        self.min_players = msg.get('min_players', 2)
                        host_text = " (你是房主)" if self.is_host else ""
                        self.update_status(f"你是 {self.my_name}{host_text}")
                        if not self.is_host:
                            self.root.after(0, lambda: self.start_button.pack_forget())
                    
                    elif msg_type == 'player_list':
                        self.update_player_list(
                            msg.get('players', []),
                            msg.get('current', 0),
                            msg.get('max', 4),
                            msg.get('min_required', 2)
                        )
                    
                    elif msg_type == 'error':
                        self.update_status(f"❌ {msg.get('message', '錯誤')}")
                    
                    elif msg_type == 'countdown':
                        count = msg.get('count')
                        self.update_timer(f"⏱️ {count}")
                        self.update_status("準備開始...")
                    
                    elif msg_type == 'game_start':
                        self.game_started = True
                        self.my_clicks = 0
                        self.switch_to_game()
                        self.update_status("開始點擊！")
                        self.update_timer(f"⏱️ {msg.get('duration')}秒")
                    
                    elif msg_type == 'update':
                        remaining = msg.get('remaining', 0)
                        self.update_timer(f"⏱️ {remaining:.1f}秒")
                        self.update_leaderboard(msg.get('rankings', []))
                    
                    elif msg_type == 'game_over':
                        self.game_started = False
                        self.show_result(
                            msg.get('your_result', '遊戲結束'),
                            msg.get('rankings', [])
                        )
                        break
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.update_status(f"錯誤: {e}")
                    break
        
        except ConnectionRefusedError:
            self.update_status("無法連線到伺服器")
        except Exception as e:
            self.update_status(f"連線錯誤: {e}")
    
    def run(self):
        net_thread = threading.Thread(target=self.network_thread, daemon=True)
        net_thread.start()
        self.root.mainloop()

def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <server_ip> <server_port> [player_name]")
        return

    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    player_name = sys.argv[3] if len(sys.argv) > 3 else "Player"
    
    client = MultiClickClient(server_ip, server_port, player_name)
    client.run()

if __name__ == "__main__":
    main()
