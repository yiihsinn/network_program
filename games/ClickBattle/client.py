#!/usr/bin/env python3
"""
ClickBattle Client - Level B (GUI 2-Player)
Tkinter GUI for clicking competition with lobby phase
"""
import sys
import socket
import json
import threading
import tkinter as tk
from tkinter import messagebox

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

class ClickBattleClient:
    def __init__(self, server_ip, server_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = None
        self.running = True
        self.game_started = False
        self.is_host = False
        self.in_lobby = True
        
        # Create GUI
        self.root = tk.Tk()
        self.root.title("點擊大戰 - ClickBattle")
        self.root.geometry("450x450")
        self.root.configure(bg='#2c3e50')
        
        # Header
        self.title_label = tk.Label(
            self.root,
            text="🎮 點擊大戰",
            font=('Arial', 24, 'bold'),
            bg='#2c3e50',
            fg='#f1c40f'
        )
        self.title_label.pack(pady=15)
        
        # Status label
        self.status_label = tk.Label(
            self.root, 
            text="連線中...",
            font=('Arial', 14),
            bg='#2c3e50',
            fg='white'
        )
        self.status_label.pack(pady=5)
        
        # Timer label (hidden during lobby)
        self.timer_label = tk.Label(
            self.root,
            text="",
            font=('Arial', 32, 'bold'),
            bg='#2c3e50',
            fg='#f1c40f'
        )
        self.timer_label.pack(pady=5)
        
        # === LOBBY FRAME ===
        self.lobby_frame = tk.Frame(self.root, bg='#2c3e50')
        self.lobby_frame.pack(pady=10, fill='x', padx=30)
        
        tk.Label(
            self.lobby_frame, 
            text="👥 玩家列表",
            font=('Arial', 16, 'bold'),
            bg='#2c3e50',
            fg='white'
        ).pack()
        
        self.player_labels = []
        for i in range(2):
            label = tk.Label(
                self.lobby_frame,
                text="⚪ 等待中...",
                font=('Arial', 14),
                bg='#2c3e50',
                fg='gray'
            )
            label.pack(pady=3)
            self.player_labels.append(label)
        
        # Start button (host only)
        self.start_button = tk.Button(
            self.lobby_frame,
            text="🚀 開始遊戲",
            font=('Arial', 16, 'bold'),
            width=15,
            height=2,
            bg='#27ae60',
            fg='white',
            activebackground='#2ecc71',
            command=self.on_start_game,
            state='disabled'
        )
        self.start_button.pack(pady=15)
        
        self.start_hint = tk.Label(
            self.lobby_frame,
            text="",
            font=('Arial', 11),
            bg='#2c3e50',
            fg='#bdc3c7'
        )
        self.start_hint.pack()
        
        # === GAME FRAME ===
        self.game_frame = tk.Frame(self.root, bg='#2c3e50')
        # Initially hidden
        
        # Click button
        self.click_button = tk.Button(
            self.game_frame,
            text="點我！",
            font=('Arial', 24, 'bold'),
            width=15,
            height=3,
            bg='#e74c3c',
            fg='white',
            activebackground='#c0392b',
            command=self.on_click,
            state='disabled'
        )
        self.click_button.pack(pady=15)
        
        # Score frame
        score_frame = tk.Frame(self.game_frame, bg='#2c3e50')
        score_frame.pack(pady=10)
        
        tk.Label(score_frame, text="你的點擊:", font=('Arial', 14), bg='#2c3e50', fg='white').grid(row=0, column=0, padx=20)
        self.my_score_label = tk.Label(score_frame, text="0", font=('Arial', 28, 'bold'), bg='#2c3e50', fg='#2ecc71')
        self.my_score_label.grid(row=1, column=0, padx=20)
        
        tk.Label(score_frame, text="對手點擊:", font=('Arial', 14), bg='#2c3e50', fg='white').grid(row=0, column=1, padx=20)
        self.opp_score_label = tk.Label(score_frame, text="0", font=('Arial', 28, 'bold'), bg='#2c3e50', fg='#e74c3c')
        self.opp_score_label.grid(row=1, column=1, padx=20)
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def on_start_game(self):
        """Host clicks Start button"""
        if self.sock and self.is_host:
            send_json(self.sock, {"type": "start_game"})
            self.start_button.config(state='disabled', text="開始中...")
    
    def on_click(self):
        if self.sock and self.game_started:
            send_json(self.sock, {"type": "click"})
    
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
    
    def update_scores(self, my_score, opp_score):
        self.root.after(0, lambda: self.my_score_label.config(text=str(my_score)))
        self.root.after(0, lambda: self.opp_score_label.config(text=str(opp_score)))
    
    def update_player_list(self, players, current, required):
        def do_update():
            for i, label in enumerate(self.player_labels):
                if i < len(players):
                    p = players[i]
                    name = p.get('name', f'Player{i+1}')
                    is_host = p.get('is_host', False)
                    icon = "👑" if is_host else "🔵"
                    host_text = " (房主)" if is_host else ""
                    label.config(text=f"{icon} {name}{host_text}", fg='#2ecc71')
                else:
                    label.config(text="⚪ 等待中...", fg='gray')
            
            # Update start button
            if self.is_host:
                if current >= 2:
                    self.start_button.config(state='normal')
                    self.start_hint.config(text="所有玩家已加入！點擊開始", fg='#2ecc71')
                else:
                    self.start_button.config(state='disabled')
                    self.start_hint.config(text=f"等待更多玩家 ({current}/{required})", fg='#bdc3c7')
            else:
                self.start_hint.config(text="等待房主開始遊戲...", fg='#bdc3c7')
        
        self.root.after(0, do_update)
    
    def switch_to_game(self):
        """Switch from lobby to game view"""
        def do_switch():
            self.lobby_frame.pack_forget()
            self.game_frame.pack(pady=10, fill='both', expand=True)
            self.click_button.config(state='normal')
        self.root.after(0, do_switch)
    
    def show_result(self, result, my_clicks, opp_clicks):
        def show():
            self.click_button.config(state='disabled', text=result)
            self.my_score_label.config(text=str(my_clicks))
            self.opp_score_label.config(text=str(opp_clicks))
            self.timer_label.config(text="遊戲結束!")
            messagebox.showinfo("遊戲結束", f"{result}\n\n你: {my_clicks} 次\n對手: {opp_clicks} 次")
            self.root.after(2000, self.on_close)
        self.root.after(0, show)
    
    def network_thread(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(60)
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
                        self.is_host = msg.get('is_host', False)
                        player_id = msg.get('player_id', 1)
                        host_text = " (你是房主)" if self.is_host else ""
                        self.update_status(f"你是 Player {player_id}{host_text}")
                        if not self.is_host:
                            self.root.after(0, lambda: self.start_button.pack_forget())
                    
                    elif msg_type == 'player_list':
                        self.update_player_list(
                            msg.get('players', []),
                            msg.get('current', 0),
                            msg.get('required', 2)
                        )
                    
                    elif msg_type == 'error':
                        self.update_status(f"❌ {msg.get('message', '錯誤')}")
                    
                    elif msg_type == 'countdown':
                        count = msg.get('count')
                        self.update_timer(f"⏱️ {count}")
                        self.update_status("準備開始...")
                    
                    elif msg_type == 'game_start':
                        self.in_lobby = False
                        self.game_started = True
                        self.switch_to_game()
                        self.update_status("開始點擊！")
                        self.update_timer(f"⏱️ {msg.get('duration')}秒")
                    
                    elif msg_type == 'update':
                        remaining = msg.get('remaining', 0)
                        self.update_timer(f"⏱️ {remaining:.1f}秒")
                        self.update_scores(msg.get('you', 0), msg.get('opponent', 0))
                    
                    elif msg_type == 'game_over':
                        self.game_started = False
                        self.show_result(
                            msg.get('your_result', '遊戲結束'),
                            msg.get('your_clicks', 0),
                            msg.get('opponent_clicks', 0)
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
        print("Usage: python client.py <server_ip> <server_port>")
        return

    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    
    client = ClickBattleClient(server_ip, server_port)
    client.run()

if __name__ == "__main__":
    main()
