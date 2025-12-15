#!/usr/bin/env python3
"""
Player Client (Lobby Client) - 玩家端 (HW3 Enhanced)
功能：註冊/登入、大廳/房間列表、商城/下載、啟動遊戲
"""

import socket
import os
import sys
import json
import getpass
import time
import subprocess
import shutil
import signal

try:
    from ..utils.protocol import ProtocolHandler, MessageBuilder
    from ..utils.utils import FileUtils
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from utils.protocol import ProtocolHandler, MessageBuilder
    from utils.utils import FileUtils

class PlayerClient:
    def __init__(self, host='127.0.0.1', port=15552):
        self.server_addr = (host, port)
        self.sock = None
        self.handler = None
        self.user_id = None
        self.user_name = None
        self.running = True
        
        # Game state tracking for room/play flow
        self.current_game_id = None
        self.current_game_version = None
        
        # Download Path
        self.download_dir = os.path.join(os.path.dirname(__file__), 'downloads')
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect(self.server_addr)
            self.handler = ProtocolHandler(self.sock)
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def send_request(self, action, data=None):
        if not self.handler: return None
        try:
            if not self.handler.send_message({"action": action, "data": data or {}}):
                return None
            response = self.handler.receive_message()
            
            # Check for force_logout (duplicate login)
            if response and response.get('type') == 'force_logout':
                print(f"\n⚠️ 你的帳號已從其他地方登入，連線被中斷")
                print(f"   原因: {response.get('reason', 'Unknown')}")
                self.user_id = None
                self.running = False
                return None
            
            return response
        except:
            return None

    def main_loop(self):
        print("=== Game Lobby - Player Console ===")
        if not self.connect():
             return

        try:
            while self.running:
                if not self.user_id:
                    self.auth_menu()
                else:
                    self.main_menu()
        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            if self.handler:
                self.send_request('logout')
            print("Goodbye!")

    def auth_menu(self):
        print("\n--- Auth ---")
        print("1. Login")
        print("2. Register")
        print("3. Exit")
        try:
            choice = input("Select: ").strip()
        except (KeyboardInterrupt, EOFError):
            self.running = False
            return
        
        if choice == '1': self.do_login()
        elif choice == '2': self.do_register()
        elif choice == '3': self.running = False
    
    def do_login(self):
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ").strip()
        res = self.send_request('login', {'email': email, 'password': password})
        if res and res['success']:
            self.user_id = res['data']['user_id']
            self.user_name = res['data']['name']
            
            # Use specific download folder for this user to support multi-player demo on one machine
            self.my_download_dir = os.path.join(self.download_dir, self.user_name) 
            if not os.path.exists(self.my_download_dir):
                os.makedirs(self.my_download_dir)
                
            print(f"Welcome, {self.user_name}!")
        else:
            print(f"Login failed: {res.get('error') if res else 'Conn Error'}")
    
    def do_register(self):
        name = input("Name: ").strip()
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ").strip()
        res = self.send_request('register', {'name': name, 'email': email, 'password': password})
        if res and res['success']: print("Registered! Please login.")
        else: print(f"Error: {res.get('error')}")

    def main_menu(self):
        print(f"\n--- Lobby ({self.user_name}) ---")
        print("1. Create Room")
        print("2. Join Room")
        print("3. Store / Download")
        print("4. Plugins")
        print("5. Logout")
        
        try:
            choice = input("Select: ").strip()
        except (KeyboardInterrupt, EOFError):
            return
            
        if choice == '1': self.create_room_flow()
        elif choice == '2': self.join_room_flow()
        elif choice == '3': self.store_menu()
        elif choice == '4': self.plugin_menu()
        elif choice == '5':
            self.send_request('logout')
            self.user_id = None
            
    def list_rooms(self):
        res = self.send_request('list_rooms')
        if res and res.get('success'):
            rooms = res['data']
            if not rooms:
                print("\nNo active rooms.")
                return []
            print("\nActive Rooms:")
            print(f"{'#':<3} {'Host':<15} {'Game':<25} {'Players':<8} {'Status'}")
            print("-" * 65)
            for idx, r in enumerate(rooms):
                host_name = r.get('host_name', r.get('hostUserId', '?')[:12])
                max_p = r.get('max_players', 2)
                print(f"{idx+1:<3} {host_name:<15} {r.get('game_name','?'):<25} {r['current_players']}/{max_p}      {r['status']}")
            return rooms
        else: 
            print("Error listing rooms")
            return []

    def list_users(self):
        res = self.send_request('list_users')
        if res:
            print("\nOnline Users:")
            for u in res['data']:
                print(f"- {u['name']} ({u['status']})")

    # --- Plugins ---
    def plugin_menu(self):
        try:
            from plugins.plugin_manager import get_manager
            manager = get_manager(self.my_download_dir)
        except Exception as e:
            print(f"Plugin system unavailable: {e}")
            return
        
        while True:
            plugins = manager.list_with_status()
            
            print("\n" + "=" * 50)
            print("           🔌 Plugin 擴充功能")
            print("=" * 50)
            
            if not plugins:
                print("目前沒有可用的 Plugin")
            else:
                print(f"{'#':<3} {'名稱':<20} {'版本':<10} {'狀態'}")
                print("-" * 50)
                for idx, p in enumerate(plugins, 1):
                    status_icon = "✅ 已安裝" if p['status'] == 'installed' else "⬜ 未安裝"
                    print(f"{idx:<3} {p['name']:<20} v{p['version']:<9} {status_icon}")
            
            print("-" * 50)
            print("輸入編號查看詳情，或 0 返回")
            
            try:
                choice = input("選擇: ").strip()
                if choice == '0':
                    break
                
                idx = int(choice) - 1
                if 0 <= idx < len(plugins):
                    self._plugin_detail(manager, plugins[idx])
            except ValueError:
                print("請輸入數字")
            except KeyboardInterrupt:
                break
    
    def _plugin_detail(self, manager, plugin):
        """Show plugin details and install/uninstall options"""
        print(f"\n=== {plugin['name']} ===")
        print(f"版本: {plugin['version']}")
        print(f"作者: {plugin.get('author', 'Unknown')}")
        print(f"說明: {plugin['description']}")
        print(f"狀態: {'✅ 已安裝' if plugin['status'] == 'installed' else '⬜ 未安裝'}")
        print("-" * 40)
        
        if plugin['status'] == 'installed':
            print("1. 移除 Plugin")
            print("2. 返回")
            c = input("選擇: ").strip()
            if c == '1':
                success, msg = manager.uninstall(plugin['id'])
                print(f"{'✅' if success else '❌'} {msg}")
        else:
            print("1. 安裝 Plugin")
            print("2. 返回")
            c = input("選擇: ").strip()
            if c == '1':
                success, msg = manager.install(plugin['id'])
                print(f"{'✅' if success else '❌'} {msg}")

    # --- Store & Download ---
    def store_menu(self):
        while True:
            print("\n--- Game Store ---")
            print("1. Browse Games")
            print("2. My Library (Local)")
            print("3. Back")
            c = input("Select: ")
            if c == '3': break
            elif c == '1': self.browse_store()
            elif c == '2': self.show_library()

    def browse_store(self):
        res = self.send_request('list_games')
        if not res or not res['success']: 
            print("Failed to load store.")
            return
        
        games = res['data']
        if not games:
            print("No games in store.")
            return

        print("\nAvailable Games:")
        for idx, g in enumerate(games):
            print(f"{idx+1}. {g['name']} (v{g['latest_version']}) by {g['author_name']}")
        
        sel = input("Select Number (or 0 back): ")
        try:
            idx = int(sel) - 1
            if idx == -1: return
            if 0 <= idx < len(games):
                self.show_game_details(games[idx]['id'])
        except: pass

    def show_game_details(self, game_id):
        res = self.send_request('get_game_details', {'game_id': game_id})
        if not res or not res.get('success'): 
            print("Failed to load game details.")
            return
        g = res['data']
        
        print(f"\n=== {g['name']} ===")
        print(f"Author: {g.get('author_name', 'Unknown')}")
        print(f"Version: {g['latest_version']}")
        print(f"Type: {g.get('type', 'Unknown')}")
        print(f"Players: {g.get('min_players', 1)}-{g.get('max_players', 2)}")
        print(f"Rating: {g.get('avg_rating', 0):.1f}/5 ({g.get('rating_count',0)} reviews)")
        print(f"Description: {g.get('description', 'No description')}")
        print("-" * 40)
        print("1. Download / Update")
        print("2. View Reviews")
        print("3. Write Review")
        print("4. Back")
        
        try:
            c = input("Select: ").strip()
        except (KeyboardInterrupt, EOFError):
            return
            
        if c == '1':
            self.download_game(game_id)
        elif c == '2':
            self.view_reviews(g)
        elif c == '3':
            self.submit_review(game_id, g['name'])

    def view_reviews(self, game_data):
        """Display reviews for a game"""
        reviews = game_data.get('reviews', [])
        if not reviews:
            print("\nNo reviews yet for this game.")
            print("Be the first to write a review!")
            return
        
        print(f"\n=== Reviews for {game_data['name']} ===")
        print(f"Average Rating: {game_data.get('avg_rating', 0):.1f}/5")
        print("-" * 50)
        for idx, r in enumerate(reviews[-10:], 1):  # Show last 10 reviews
            stars = "★" * r['score'] + "☆" * (5 - r['score'])
            print(f"{idx}. {stars} ({r['score']}/5)")
            if r.get('comment'):
                print(f"   \"{r['comment'][:100]}{'...' if len(r.get('comment','')) > 100 else ''}\"")
            print()
        
        input("Press Enter to continue...")

    def submit_review(self, game_id, game_name):
        """Submit a review for a game with validation and error handling"""
        # Check if player has played this game (check local library)
        local_ver = self._get_local_version(game_id)
        if not local_ver:
            print("\n❌ 您尚未下載過此遊戲，無法評論。")
            print("   請先下載並遊玩後再評論。")
            return
        
        print(f"\n=== 評論 {game_name} ===")
        print("(評分範圍: 1-5 分)")
        
        # Get score with validation
        score = None
        while score is None:
            try:
                score_input = input("評分 (1-5): ").strip()
                if not score_input:
                    print("已取消")
                    return
                score = int(score_input)
                if score < 1 or score > 5:
                    print("❌ 評分必須在 1 到 5 之間")
                    score = None
            except ValueError:
                print("❌ 請輸入數字 (1-5)")
        
        # Get comment with length limit
        print("\n評論 (可選，最多 500 字，留空略過):")
        comment = input("> ").strip()
        if len(comment) > 500:
            print(f"⚠️ 評論過長 ({len(comment)} 字)，將截斷至 500 字")
            comment = comment[:500]
        
        # Confirm
        stars = "★" * score + "☆" * (5 - score)
        print(f"\n--- 確認評論 ---")
        print(f"評分: {stars} ({score}/5)")
        if comment:
            print(f"評論: {comment[:50]}{'...' if len(comment) > 50 else ''}")
        
        confirm = input("\n送出評論? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        # Submit to server
        print("正在送出評論...")
        res = self.send_request('submit_review', {
            'game_id': game_id,
            'score': score,
            'comment': comment
        })
        
        if res and res.get('success'):
            print("✅ 評論已送出！感謝您的回饋。")
        else:
            error = res.get('error') if res else '連線錯誤'
            print(f"❌ 送出失敗: {error}")
            # Offer retry
            retry = input("是否重試? (y/n): ").strip().lower()
            if retry == 'y':
                # Retry with saved data
                res = self.send_request('submit_review', {
                    'game_id': game_id,
                    'score': score,
                    'comment': comment
                })
                if res and res.get('success'):
                    print("✅ 評論已送出！")
                else:
                    print("❌ 仍然失敗，請稍後再試。")

    def download_game(self, game_id):
        print(f"Downloading {game_id}...")
        res = self.send_request('download_game', {'game_id': game_id})
        if not res or not res['success']:
            print(f"Download Error: {res.get('error') if res else 'Net Error'}")
            return
            
        data = res['data']
        version = data['version']
        b64 = data['file_content_base64']
        
        # Save to local library: downloads/<User>/<game_id>/<version>/
        dest = os.path.join(self.my_download_dir, game_id, version)
        
        if FileUtils.unzip_data(b64, dest):
            # Update meta
            meta_path = os.path.join(self.my_download_dir, game_id, 'meta.json')
            with open(meta_path, 'w') as f:
                json.dump({'latest_local': version}, f)
            print("Download Complete!")
        else:
            print("Corrupted file.")

    def show_library(self):
        if not os.path.exists(self.my_download_dir):
            print("圖書館是空的，請先下載遊戲！")
            return
        
        # Get all local games
        local_games = []
        for gid in os.listdir(self.my_download_dir):
            game_dir = os.path.join(self.my_download_dir, gid)
            if not os.path.isdir(game_dir):
                continue
            
            meta_p = os.path.join(game_dir, 'meta.json')
            local_ver = "?"
            if os.path.exists(meta_p):
                with open(meta_p, encoding='utf-8') as f:
                    local_ver = json.load(f).get('latest_local', '?')
            
            # Try to get game name from game_config.json
            config_path = os.path.join(game_dir, local_ver, 'game_config.json')
            game_name = gid[:20]  # Default to ID
            game_type = "?"
            if os.path.exists(config_path):
                try:
                    with open(config_path, encoding='utf-8') as f:
                        cfg = json.load(f)
                        game_name = cfg.get('name', game_name)
                        game_type = cfg.get('type', '?')
                except:
                    pass
            
            local_games.append({
                'id': gid,
                'name': game_name,
                'type': game_type,
                'local_version': local_ver
            })
        
        if not local_games:
            print("圖書館是空的，請先下載遊戲！")
            return
        
        # Query server for latest versions
        print("\n正在檢查更新...")
        res = self.send_request('list_games')
        server_games = {}
        if res and res.get('success'):
            for g in res['data']:
                server_games[g['id']] = g.get('latest_version', '?')
        
        # Display library
        print("\n" + "=" * 65)
        print("                    📚 我的遊戲庫")
        print("=" * 65)
        print(f"{'#':<3} {'遊戲名稱':<20} {'類型':<6} {'本地版本':<10} {'狀態'}")
        print("-" * 65)
        
        for idx, game in enumerate(local_games):
            gid = game['id']
            local_v = game['local_version']
            server_v = server_games.get(gid)
            
            # Determine status
            if server_v is None:
                status = "⚠️ 已下架"
            elif server_v == local_v:
                status = "✅ 最新"
            else:
                status = f"🔄 有更新 (v{server_v})"
            
            print(f"{idx+1:<3} {game['name']:<20} {game['type']:<6} v{local_v:<9} {status}")
        
        print("-" * 65)
        print(f"共 {len(local_games)} 個遊戲")
        print("=" * 65)

    def _get_local_version(self, game_id):
        meta_p = os.path.join(self.my_download_dir, game_id, 'meta.json')
        if os.path.exists(meta_p):
             with open(meta_p) as f: return json.load(f).get('latest_local')
        return None

    # --- Room & Play ---
    def create_room_flow(self):
        # 1. Select Game from Library (Or Store? Ideally Store list to ensure valid ID)
        res = self.send_request('list_games') # Get valid list
        if not res or not res.get('success'): 
            print("Failed to load games.")
            return
        games = res['data']
        if not games:
            print("No games available in store.")
            return
        
        print("\nSelect Game to Host (0 to cancel):")
        for idx, g in enumerate(games):
             print(f"{idx+1}. {g['name']} (v{g['latest_version']})")
        
        try:
            sel = input("Choice: ").strip()
            idx = int(sel) - 1
            if idx == -1:
                return
            if idx < 0 or idx >= len(games):
                print("Invalid selection.")
                return
            g = games[idx]
        except (ValueError, KeyboardInterrupt): 
            return
        
        # Check if we have it
        local_v = self._get_local_version(g['id'])
        if local_v != g['latest_version']:
            print(f"Download required! Server: {g['latest_version']}, Local: {local_v or 'Not installed'}")
            dl = input("Download now? (y/n): ")
            if dl.lower() == 'y':
                self.download_game(g['id'])
                local_v = self._get_local_version(g['id']) # Recheck
                if local_v != g['latest_version']: 
                    print("Download failed.")
                    return # Failed
            else:
                return

        # Store game state for later use
        self.current_game_id = g['id']
        self.current_game_version = g['latest_version']

        # Request Create
        res = self.send_request('create_room', {'game_id': g['id']})
        if res and res.get('success'):
            room_id = res['data']['room_id']
            print(f"Room {room_id} created. Waiting for player...")
            self.room_wait_loop(is_host=True)  # Host can start game
        else:
            print(f"Create failed: {res.get('error') if res else 'Connection error'}")


    def join_room_flow(self):
        rooms = self.list_rooms()
        if not rooms: 
            return
        
        # Select by number instead of typing room ID
        print("\nSelect room number to join (0 to cancel):")
        try:
            choice = input("Room #: ").strip()
            idx = int(choice) - 1
            if idx == -1:  # User chose 0
                return
            if idx < 0 or idx >= len(rooms):
                print("Invalid selection.")
                return
        except (ValueError, KeyboardInterrupt):
            return
        
        target_room = rooms[idx]
        rid = target_room['id']
        game_id = target_room.get('game_id')
        game_ver = target_room.get('game_version')
        
        # Check if we have the required game version
        if game_id and game_ver:
            local_v = self._get_local_version(game_id)
            if local_v != game_ver:
                print(f"This room requires {target_room.get('game_name', game_id)} v{game_ver}")
                print(f"Your version: {local_v or 'Not installed'}")
                dl = input("Download now? (y/n): ")
                if dl.lower() == 'y':
                    self.download_game(game_id)
                    local_v = self._get_local_version(game_id)
                    if local_v != game_ver:
                        print("Download failed or wrong version.")
                        return
                else:
                    return
        
        # Store game info for later use
        self.current_game_id = game_id
        self.current_game_version = game_ver
        
        # Send join request with version
        res = self.send_request('join_room', {
            'room_id': rid, 
            'client_game_version': game_ver
        })
        
        if not res:
            print("Connection error.")
            return
        
        if res.get('success'):
            print("Joined room! Waiting for host to start...")
            print("(Press Ctrl+C to leave room)")
            self.room_wait_loop()
        else:
            # Handle version mismatch error from server
            if res.get('error') == 'Version Mismatch':
                req_ver = res.get('required_version')
                req_gam = res.get('game_id')
                print(f"Version mismatch! Server requires v{req_ver}")
                dl = input("Download and retry? (y/n): ")
                if dl.lower() == 'y':
                    self.download_game(req_gam)
                    # Retry
                    res = self.send_request('join_room', {
                        'room_id': rid, 
                        'client_game_version': req_ver
                    })
                    if res and res.get('success'):
                        self.current_game_id = req_gam
                        self.current_game_version = req_ver
                        print("Joined room!")
                        self.room_wait_loop()
                        return
            print(f"Join failed: {res.get('error', 'Unknown error')}")


    def room_wait_loop(self, is_host=False):
        """Wait for game to start. Host can type 'start' to start the game."""
        import threading
        import queue
        
        # Check if chat plugin is installed (per-user)
        chat_enabled = False
        try:
            from plugins.plugin_manager import get_manager
            chat_enabled = get_manager(self.my_download_dir).is_installed('room_chat')
        except:
            pass
        
        print("(Press Ctrl+C to Leave Room)")
        if is_host:
            print("\n--- Host Commands ---")
            print("1. Start Game")
            print("2. Show Players")
            print("3. Leave Room")
            if chat_enabled:
                print("c. Chat (輸入 c 後輸入訊息)")
        else:
            if chat_enabled:
                print("\n💬 聊天 Plugin 已啟用 - 輸入 c 發送訊息")
        
        # Track room players
        room_players = []
        
        # Set socket timeout for interruptibility
        original_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.5)
        
        # Use a command queue instead of direct network calls from input thread
        command_queue = queue.Queue()
        should_exit = False
        
        # Input thread only puts commands into queue, doesn't touch network
        def host_input_thread():
            nonlocal should_exit
            while not should_exit:
                try:
                    user_input = input("Select: " if is_host else "> ").strip()
                    if user_input == '1' and is_host:
                        command_queue.put('start')
                    elif user_input == '2' and is_host:
                        command_queue.put('list')
                    elif user_input == '3' and is_host:
                        command_queue.put('leave')
                        break
                    elif user_input.lower() == 'c' and chat_enabled:
                        # Enter chat mode
                        msg = input("💬 訊息: ").strip()
                        if msg:
                            command_queue.put(('chat', msg))
                except EOFError:
                    break
                except Exception:
                    break
        
        input_thread = None
        if is_host or chat_enabled:
            input_thread = threading.Thread(target=host_input_thread, daemon=True)
            input_thread.start()
        
        try:
            while not should_exit:
                # Process any pending commands from input thread
                try:
                    cmd = command_queue.get_nowait()
                    if cmd == 'start':
                        print("Requesting game start...")
                        self.sock.settimeout(5.0)
                        res = self.send_request('start_game')
                        self.sock.settimeout(0.5)
                        if res and res.get('success'):
                            # Host gets game server info directly in response
                            ip = res.get('game_server_ip')
                            port = res.get('game_server_port')
                            print("*** Game Started!! Launching Client... ***")
                            self.sock.settimeout(None)
                            should_exit = True
                            self.launch_game_client(ip, port)
                            print("Game Session Ended. Returning to Lobby...")
                            break
                        else:
                            err = res.get('error') if res else 'Connection error'
                            print(f"Cannot start: {err}")
                    elif cmd == 'list':
                        # Show current room players
                        print(f"\n--- Room Players ({len(room_players) + 1}) ---")
                        print(f"1. {self.user_name} (Host, you)")
                        for i, player in enumerate(room_players, 2):
                            print(f"{i}. {player}")
                        print("---")
                    elif cmd == 'leave':
                        self.send_request('leave_room')
                        should_exit = True
                        break
                    elif isinstance(cmd, tuple) and cmd[0] == 'chat':
                        # Send chat message (Plugin feature)
                        self.sock.settimeout(2.0)
                        res = self.send_request('room_chat', {'message': cmd[1]})
                        self.sock.settimeout(0.5)
                        if res and res.get('success'):
                            print(f"💬 [你]: {cmd[1]}")
                except queue.Empty:
                    pass  # No commands pending
                
                # Check for incoming messages with timeout
                try:
                    msg = self.handler.receive_message()
                    if msg is None:
                        continue  # Timeout, loop again
                    elif not msg or (isinstance(msg, dict) and not msg):
                        print("Disconnected from server.")
                        self.running = False
                        break
                    elif isinstance(msg, dict):
                        msg_type = msg.get('type')
                        
                        if msg_type == 'user_joined':
                            player_name = msg.get('user_name', 'Unknown')
                            room_players.append(player_name)
                            print(f"\n*** {player_name} joined! ({len(room_players) + 1} players) ***")
                            if is_host:
                                print("Select: 1=Start, 2=List, 3=Leave")
                        elif msg_type == 'user_left':
                            player_name = msg.get('user_name', 'Unknown')
                            if player_name in room_players:
                                room_players.remove(player_name)
                            print(f"\n*** {player_name} left. ({len(room_players) + 1} players) ***")
                        elif msg_type == 'game_started':
                            print("\n*** Game Started!! Launching Client... ***")
                            ip = msg.get('game_server_ip')
                            port = msg.get('game_server_port')
                            self.sock.settimeout(original_timeout)
                            should_exit = True
                            self.launch_game_client(ip, port)
                            print("Game Session Ended. Returning to Lobby...")
                            break
                        elif msg_type == 'force_logout':
                            print("Logged out by another session.")
                            self.running = False
                            break
                        elif msg_type == 'room_chat':
                            # Plugin: Room Chat message received
                            sender = msg.get('sender', 'Unknown')
                            message = msg.get('message', '')
                            timestamp = msg.get('timestamp', '')
                            print(f"\n💬 [{sender}] ({timestamp}): {message}")
                except socket.timeout:
                    continue  # Normal timeout, check queue and loop
                except Exception as e:
                    if "timed out" not in str(e).lower():
                        print(f"Error: {e}")
                        break
                        
        except KeyboardInterrupt:
            print("\nLeaving room...")
            self.sock.settimeout(5.0)
            self.send_request('leave_room')
        finally:
            should_exit = True
            self.sock.settimeout(original_timeout)

    def launch_game_client(self, ip, port):
        """Launch the game client using stored game state"""
        if not self.current_game_id or not self.current_game_version:
            print("Error: Game info not available!")
            return
            
        self.launch_game_client_impl(
            self.current_game_id, 
            ip, 
            port, 
            self.current_game_version
        )

    def launch_game_client_impl(self, game_id, ip, port, version):
        """Real launch implementation"""
        game_dir = os.path.join(self.my_download_dir, game_id, version)
        if not os.path.exists(game_dir):
            print(f"Game files missing at {game_dir}!")
            return
            
        config_path = os.path.join(game_dir, 'game_config.json')
        try:
            with open(config_path, encoding='utf-8') as f: 
                cfg = json.load(f)
        except FileNotFoundError:
            print("game_config.json not found!")
            return
        
        exe_cmd = cfg.get('exe_cmd', ['python', 'client.py'])
        
        # Convention: Game receives IP PORT PLAYER_NAME as arguments
        full_cmd = exe_cmd + [str(ip), str(port), self.user_name]
        
        print(f"Launching: {' '.join(full_cmd)}")
        print(f"Game directory: {game_dir}")
        print("-" * 40)
        
        try:
            # On Windows, create a new console to avoid stdin interference
            import platform
            if platform.system() == 'Windows':
                # CREATE_NEW_CONSOLE = 0x00000010
                subprocess.run(full_cmd, cwd=game_dir, creationflags=0x00000010)
            else:
                subprocess.run(full_cmd, cwd=game_dir)
        except Exception as e:
            print(f"Failed to launch game: {e}")
            return
        
        print("-" * 40)
        # After run -> Suggest Review
        self.review_menu(game_id)

    def review_menu(self, game_id):
        print("\n--- Review Game ---")
        yn = input("Submit a review? (y/n) ")
        if yn.lower() != 'y': return
        
        score = int(input("Score (1-5): "))
        cmt = input("Comment: ")
        
        self.send_request('submit_review', {'game_id': game_id, 'score': score, 'comment': cmt})
        print("Review submitted.")

if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    PlayerClient(host=host).main_loop()
