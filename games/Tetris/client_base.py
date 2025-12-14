#!/usr/bin/env python3


import argparse
import io
import math
import queue
import socket
import struct
import threading
import time
import wave
from typing import Any, Dict, List, Optional, Tuple

import pygame

from protocol import ProtocolHandler

COLORS = {
    0: (10, 10, 16),
    1: (0, 240, 240),
    2: (240, 240, 0),
    3: (160, 0, 240),
    4: (0, 240, 0),
    5: (240, 0, 0),
    6: (0, 0, 240),
    7: (240, 160, 0),
}

SHAPES = {
    "I": [[1, 1, 1, 1]],
    "O": [[1, 1], [1, 1]],
    "T": [[0, 1, 0], [1, 1, 1]],
    "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]],
    "J": [[1, 0, 0], [1, 1, 1]],
    "L": [[0, 0, 1], [1, 1, 1]],
}

INPUT_MAPPING = {
    pygame.K_LEFT: "LEFT",
    pygame.K_RIGHT: "RIGHT",
    pygame.K_DOWN: "DOWN",
    pygame.K_UP: "CW",
    pygame.K_z: "CCW",
    pygame.K_SPACE: "HARD_DROP",
    pygame.K_c: "HOLD",
}


class GameClient:
    # 建構子：初始化 CLI 與遊戲客戶端狀態（連線資訊、使用者/房間快取、遊戲狀態等）
    # 輸入: lobby_host, lobby_port。副作用: 初始化多個屬性與執行緒相關變數。
    def __init__(self, lobby_host: str, lobby_port: int) -> None:
        self.lobby_host = lobby_host
        self.lobby_port = lobby_port
        self.lobby_handler: Optional[ProtocolHandler] = None
        self.connected_to_lobby = False
        self.user_id: Optional[str] = None
        self.user_name: Optional[str] = None
        self.credentials: Dict[str, str] = {}
        self.user_directory: Dict[str, Dict[str, str]] = {}
        self.room_members: Dict[str, List[str]] = {}
        self.pending_invitations: Dict[str, Dict[str, Any]] = {}

        self.request_lock = threading.Lock()
        self.response_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.pending_request: Optional[str] = None

        self.listener_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.heartbeat_running = False
        self.cli_thread: Optional[threading.Thread] = None
        self.running = True

        # Lobby state
        self.current_room_id: Optional[str] = None

        # Game state
        self.game_handler: Optional[ProtocolHandler] = None
        self.connected_to_game = False
        self.role: Optional[str] = None
        self.game_state_lock = threading.Lock()
        self.my_board = [[0 for _ in range(10)] for _ in range(20)]
        self.opp_board = [[0 for _ in range(10)] for _ in range(20)]
        self.my_state: Dict[str, Any] = {"score": 0, "lines": 0, "level": 1, "current": None, "next": [], "hold": None, "x": 4, "y": 0, "rot": 0}
        self.opp_state: Dict[str, Any] = {"score": 0, "lines": 0, "level": 1, "current": None, "x": 4, "y": 0, "rot": 0}
        self.game_started_at: Optional[float] = None
        self.game_results: Optional[Dict[str, Any]] = None
        self.round_duration: float = 90.0
        self.read_only = False
        self.spectating_room_id: Optional[str] = None
        self.player_slots: List[str] = []
        self.primary_player_id: Optional[str] = None
        self.secondary_player_id: Optional[str] = None

        self.game_launch_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.sound_effects: Dict[str, Optional[pygame.mixer.Sound]] = {
            "hard_drop": None,
            "line_clear": None,
        }
        self.audio_ready = False
        self.last_line_count = 0
        self.effects = {
            "hard_drop": 0.0,
            "line_flash": 0.0,
        }

    # ---------------- Lobby connection ---------------- #

    # 登入流程：連到 Lobby, 發送 login 請求並在成功後啟動 listener/heartbeat
    # 輸入: email, password。回傳: True 表示登入成功，並初始化 self.user_id/self.user_name。
    def login(self, email: str, password: str) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.lobby_host, self.lobby_port))
            handler = ProtocolHandler(sock)
            payload = {
                "type": "login",
                "data": {"email": email, "password": password},
            }
            if not handler.send_message(payload):
                handler.close()
                print("[Client] Failed to send login request.")
                return False
            response = handler.receive_message()
            if not response or not response.get("success"):
                handler.close()
                error = response.get("error") if response else "no response"
                print(f"[Client] Login failed: {error}")
                return False
        except Exception as exc:  # noqa: BLE001
            print(f"[Client] Login error: {exc}")
            return False

        self.lobby_handler = handler
        self.connected_to_lobby = True
        try:
            handler.sock.settimeout(None)
        except Exception:  # noqa: BLE001
            pass
        data = response.get("data", {})
        self.user_id = data.get("user_id")
        self.user_name = data.get("name", "Player")
        self.credentials = {"email": email, "password": password}
        self.remember_user(self.user_id, name=self.user_name, email=email)
        print(f"[Client] Logged in as {self.user_name} ({self.user_id})")

        self.listener_thread = threading.Thread(target=self.lobby_listener, daemon=True)
        self.listener_thread.start()
        # 快速同步使用者名錄，方便後續顯示名稱
        self.refresh_user_directory(silent=True)
        self.start_heartbeat()
        return True

    # 登出流程：通知 Lobby 並關閉連線、停止 heartbeat，清理本地使用者狀態。
    # 輸入: 無。副作用: 清除 self.lobby_handler、停止執行緒並重設 user 狀態。
    def logout(self) -> None:
        if not self.connected_to_lobby or not self.lobby_handler:
            return
        response = self.send_request({"type": "logout", "data": {}}, quiet=True)
        if response and response.get("success"):
            print("[Client] Logged out.")
        if self.lobby_handler:
            try:
                self.lobby_handler.close()
            except Exception:  # noqa: BLE001
                pass
        self.connected_to_lobby = False
        self.lobby_handler = None
        self.user_id = None
        self.user_name = None
        self.current_room_id = None
        self.stop_heartbeat()

    # 註冊使用者：向 Lobby 發送 register 請求並等待回應，成功後提示使用者登入。
    # 輸入: name, email, password。回傳: True 表示註冊成功。
    def register(self, name: str, email: str, password: str) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.lobby_host, self.lobby_port))
            handler = ProtocolHandler(sock)
            payload = {
                "type": "register",
                "data": {"name": name, "email": email, "password": password},
            }
            if not handler.send_message(payload):
                handler.close()
                print("[Client] Failed to send register request.")
                return False
            response = handler.receive_message()
            handler.close()
            if not response or not response.get("success"):
                error = response.get("error") if response else "no response"
                print(f"[Client] Register failed: {error}")
                return False
            print("[Client] Register success, please login.")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[Client] Register error: {exc}")
            return False

    # Lobby listener 迴圈：接收非同步推送或回應，並分流到 response_queue 或 handle_push
    # 輸入: 無（使用 self.lobby_handler）。副作用: 將訊息放入 response_queue 或呼叫 handle_push。
    def lobby_listener(self) -> None:
        assert self.lobby_handler is not None
        while self.connected_to_lobby:
            try:
                message = self.lobby_handler.receive_message()
                if not message:
                    print("[Client] Lobby connection closed.")
                    break
                if message.get("type") == "pong":
                    continue
                if self.pending_request and "success" in message:
                    self.response_queue.put(message)
                    self.pending_request = None
                else:
                    self.handle_push(message)
            except Exception as exc:  # noqa: BLE001
                print(f"[Client] Lobby listener error: {exc}")
                break
        self.connected_to_lobby = False
        self.lobby_handler = None
        self.pending_request = None
        self.stop_heartbeat()
        print("[Client] Disconnected from lobby.")

    # 啟動 heartbeat 執行緒以維持與 Lobby 的長連線（定期發送 ping）
    # 輸入: 無。副作用: 建立並啟動 heartbeat_thread。
    def start_heartbeat(self) -> None:
        if self.heartbeat_running:
            return
        self.heartbeat_running = True
        self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

    # 停止 heartbeat 執行緒並等待其結束
    # 輸入: 無。副作用: 將 heartbeat_running 設為 False 並嘗試 join thread。
    def stop_heartbeat(self) -> None:
        self.heartbeat_running = False
        thread = self.heartbeat_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self.heartbeat_thread = None

    # heartbeat 迴圈：每 15 秒發送 ping，使用 request_lock 保護發送時機
    # 輸入: 無（依賴 self.lobby_handler）。副作用: 呼叫 handler.send_message(ping)。
    def heartbeat_loop(self) -> None:
        while self.heartbeat_running:
            time.sleep(15.0)
            if not self.heartbeat_running:
                break
            if not self.connected_to_lobby or not self.lobby_handler:
                continue
            acquired = False
            try:
                acquired = self.request_lock.acquire(timeout=0.2)
                if not acquired:
                    continue
                payload = {"type": "ping", "ts": int(time.time() * 1000)}
                self.lobby_handler.send_message(payload)
            except Exception:  # noqa: BLE001
                # Ignore ping failures; listener thread will detect disconnect.
                pass
            finally:
                if acquired:
                    self.request_lock.release()

    def remember_user(self, user_id: Optional[str], *, name: Optional[str] = None, email: Optional[str] = None) -> None:
        if not user_id:
            return
        entry = self.user_directory.setdefault(user_id, {})
        if name:
            entry['name'] = name
        if email:
            entry['email'] = email

    def refresh_user_directory(self, silent: bool = False) -> Optional[List[Dict[str, Any]]]:
        if not self.connected_to_lobby or not self.lobby_handler:
            return None
        response = self.send_request({"type": "list_online_users", "data": {}}, quiet=True)
        if not response or not response.get("success"):
            if not silent:
                print("[Client] 無法更新線上使用者列表。")
            return None
        users = response.get("data", []) or []
        for user in users:
            self.remember_user(user.get('user_id'), name=user.get('name'), email=user.get('email'))
        return users

    def resolve_user_display(self, user_id: Optional[str]) -> str:
        if not user_id:
            return "未知玩家"
        entry = self.user_directory.get(user_id)
        if entry:
            name = entry.get('name')
            email = entry.get('email')
            if name and email:
                return f"{name} <{email}>"
            if name:
                return name
            if email:
                return f"<{email}>"
        return user_id[:8] + "..." if len(user_id) > 8 else user_id

    def resolve_user_matches(self, keyword: str) -> List[Tuple[str, Dict[str, str]]]:
        keyword = keyword.strip().lower()
        if not keyword:
            return []
        matches: List[Tuple[str, Dict[str, str]]] = []
        for user_id, info in self.user_directory.items():
            name = info.get('name', '')
            email = info.get('email', '')
            if (keyword in user_id.lower() or
                    keyword in name.lower() or
                    keyword in email.lower()):
                matches.append((user_id, info))
        # Prefer exact id/email matches first
        matches.sort(key=lambda item: (
            0 if item[0].lower().startswith(keyword) else 1,
            0 if (item[1].get('email', '').lower().startswith(keyword)) else 1,
            item[1].get('name', '').lower()
        ))
        return matches

    def handle_join_success(self, fallback_room_id: Optional[str], response: Dict[str, Any]) -> Optional[str]:
        if not response or not response.get("success"):
            return None
        room_data = response.get("data", {}) or {}
        room_id = room_data.get("id") or fallback_room_id
        if room_id:
            members = room_data.get("users") or []
            if members:
                self.room_members[room_id] = list(members)
            else:
                self.room_members[room_id] = [self.user_id] if self.user_id else []
            for uid in members:
                self.remember_user(uid)
        host_id = room_data.get("hostUserId")
        host_name = room_data.get("host_name")
        if host_id and host_name:
            self.remember_user(host_id, name=host_name)
        if room_id and not room_data:
            self.room_members.pop(room_id, None)
        self.current_room_id = room_id
        return room_id

    # 取得公開房間列表：向 Lobby 發送 list_rooms 並回傳 normalized 的房間資料
    # 輸入: quiet。回傳: 房間資料列表或 None。
    def fetch_rooms(self, *, quiet: bool = False) -> Optional[List[Dict[str, Any]]]:
        response = self.send_request({"type": "list_rooms", "data": {}}, quiet=True)
        if not response or not response.get("success"):
            if not quiet:
                print("[Client] Failed to list rooms.")
            return None

        rooms = response.get("data", []) or []
        normalized: List[Dict[str, Any]] = []
        for room in rooms:
            room_info = dict(room or {})
            users = room_info.get("users") or []
            user_names = room_info.get("user_names") or []
            for uid, uname in zip(users, user_names):
                self.remember_user(uid, name=uname)
            host_id = room_info.get("hostUserId")
            host_name = room_info.get("host_name")
            if host_id and host_name:
                self.remember_user(host_id, name=host_name)
            if "status" not in room_info:
                room_info["status"] = "idle"
            if "is_joinable_public" not in room_info:
                visibility = room_info.get("visibility", "public")
                is_open = bool(room_info.get("is_open", len(users) < 2))
                room_info["is_joinable_public"] = is_open and visibility != "private"
            normalized.append(room_info)
        return normalized

    # 取得正在進行的比賽（實況房間）：向 Lobby 請求 list_live_rooms 並回傳 normalized list
    # 輸入: quiet。回傳: live room 列表或 None。
    def fetch_live_rooms(self, *, quiet: bool = False) -> Optional[List[Dict[str, Any]]]:
        response = self.send_request({"type": "list_live_rooms", "data": {}}, quiet=True)
        if not response or not response.get("success"):
            if not quiet:
                print("[Client] Failed to list active matches.")
            return None

        rooms = response.get("data", []) or []
        normalized: List[Dict[str, Any]] = []
        for room in rooms:
            room_info = dict(room or {})
            users = room_info.get("players") or room_info.get("users") or []
            user_names = room_info.get("playerNames") or room_info.get("user_names") or []
            for uid, uname in zip(users, user_names):
                self.remember_user(uid, name=uname)
            host_id = room_info.get("hostUserId")
            host_name = room_info.get("host_name")
            if host_id and host_name:
                self.remember_user(host_id, name=host_name)
            normalized.append(room_info)
        return normalized

    # 在線上使用者候選尋找：從 DB 同步的 users 中過濾出符合關鍵字且在線者
    # 輸入: keyword。回傳: 使用者 dict 列表（符合條件且在線）。
    def find_online_user_candidates(self, keyword: str) -> List[Dict[str, Any]]:
        needle = keyword.strip().lower()
        if not needle:
            return []
        users = self.refresh_user_directory(silent=True) or []
        matches: List[Dict[str, Any]] = []
        for user in users:
            if not user.get("online"):
                continue
            name = (user.get("name") or "").lower()
            email = (user.get("email") or "").lower()
            uid = (user.get("user_id") or "").lower()
            if needle in name or needle in email or needle in uid:
                matches.append(user)

        def sort_key(user: Dict[str, Any]) -> Tuple[int, int, int, int, str]:
            name = (user.get("name") or "").lower()
            email = (user.get("email") or "").lower()
            uid = (user.get("user_id") or "").lower()
            return (
                0 if email == needle else 1,
                0 if uid == needle else 1,
                0 if name == needle else 1,
                0 if email.startswith(needle) else 1,
                name,
            )

        matches.sort(key=sort_key)
        return matches

    # 取得本地或 Lobby 的邀請清單，並過濾過期邀請（5 分鐘）
    # 輸入: quiet。回傳: 有效的邀請列表。
    def fetch_invitations(self, *, quiet: bool = False) -> List[Dict[str, Any]]:
        response = self.send_request({"type": "list_invitations", "data": {}}, quiet=True)
        invites: List[Dict[str, Any]] = []
        if response and response.get("success"):
            invites = response.get("data", []) or []
        else:
            if not quiet:
                if self.pending_invitations:
                    print("[Client] 無法取得最新邀請列表，改用本地快取。")
                else:
                    print("[Client] 無法取得邀請列表。")
            invites = list(self.pending_invitations.values())

        now = time.time()
        refreshed: Dict[str, Dict[str, Any]] = {}
        for inv in invites:
            room_id = inv.get("room_id")
            if not room_id:
                continue
            ts = inv.get("timestamp")
            if ts and now - ts > 300:
                continue
            from_id = inv.get("from_user_id")
            from_name = inv.get("from_user_name")
            if from_id:
                self.remember_user(from_id, name=from_name)
            refreshed[room_id] = inv

        self.pending_invitations = refreshed
        ordered = sorted(refreshed.values(), key=lambda item: item.get("timestamp", now))
        return ordered

    def format_invitation_summary(self, invitation: Dict[str, Any]) -> str:
        room_id = invitation.get("room_id", "-")
        label = self.resolve_user_display(invitation.get("from_user_id"))
        ts = invitation.get("timestamp")
        age = "?"
        if ts:
            delta = time.time() - ts
            if delta < 60:
                age = f"{int(delta)} 秒前"
            elif delta < 3600:
                age = f"{int(delta // 60)} 分鐘前"
            else:
                age = f"{int(delta // 3600)} 小時前"
        return f"房間 {room_id} | 來自 {label} | {age}"

    def select_invitation(self, invites: List[Dict[str, Any]], token: Optional[str], action_label: str) -> Tuple[Optional[Dict[str, Any]], bool]:
        if not invites:
            return None, False
        if token:
            target = token.strip().lower()
            matches = [inv for inv in invites if (inv.get("room_id", "").lower().startswith(target))]
            if not matches:
                return None, False
            candidates = matches
        else:
            candidates = invites

        if len(candidates) == 1 and token:
            return candidates[0], False

        print("\n邀請列表：")
        for idx, invitation in enumerate(candidates, start=1):
            print(f"  {idx}) {self.format_invitation_summary(invitation)}")

        choice = input(f"選擇要{action_label}的邀請編號 (Enter 取消): ").strip()
        if not choice:
            print(f"[Client] 已取消{action_label}操作。")
            return None, True
        if not choice.isdigit():
            print("[Client] 無效的選項。")
            return None, False
        index = int(choice) - 1
        if index < 0 or index >= len(candidates):
            print("[Client] 選項超出範圍。")
            return None, False
        return candidates[index], False

    def format_match_results(self, results: List[Dict[str, Any]]) -> List[str]:
        formatted: List[str] = []
        for entry in results:
            user_id = entry.get('userId') or entry.get('user_id')
            label = self.resolve_user_display(user_id)
            lines_cleared = entry.get('lines', 0)
            filled = entry.get('filledCells') if 'filledCells' in entry else entry.get('filled_cells')
            is_winner = bool(entry.get('winner'))
            status = "🏆" if is_winner else ""
            # 不再顯示 score 與 level，僅顯示消行與（若有）剩餘塗色格數
            if filled is not None:
                formatted.append(f"{status} {label}: 消行 {lines_cleared}, 塗色 {filled}".strip())
            else:
                formatted.append(f"{status} {label}: 消行 {lines_cleared}".strip())
        return formatted

    def send_request(self, message: Dict[str, Any], timeout: float = 5.0, quiet: bool = False) -> Optional[Dict[str, Any]]:
        if not self.connected_to_lobby or not self.lobby_handler:
            if not quiet:
                print("[Client] Not connected to lobby.")
            return None
        with self.request_lock:
            while not self.response_queue.empty():
                try:
                    self.response_queue.get_nowait()
                except queue.Empty:
                    break
            self.pending_request = message.get("type")
            if not self.lobby_handler.send_message(message):
                self.pending_request = None
                if not quiet:
                    print("[Client] Failed to send lobby request.")
                return None
        try:
            response = self.response_queue.get(timeout=timeout)
            return response
        except queue.Empty:
            if not quiet:
                print("[Client] Lobby request timeout.")
            with self.request_lock:
                self.pending_request = None
            return None

    def handle_push(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "user_joined":
            user_id = message.get('user_id')
            name = message.get('name')
            self.remember_user(user_id, name=name)
            if self.current_room_id:
                members = self.room_members.setdefault(self.current_room_id, [])
                if user_id and user_id not in members:
                    members.append(user_id)
            print(f"[Lobby] {self.resolve_user_display(user_id)} 加入房間。")
        elif msg_type == "user_left":
            user_id = message.get('user_id')
            for members in self.room_members.values():
                if user_id in members:
                    members.remove(user_id)
            print(f"[Lobby] {self.resolve_user_display(user_id)} 離開房間。")
        elif msg_type == "invitation":
            data = message.get("data", {})
            from_id = data.get('from_user_id')
            from_name = data.get('from_user_name')
            self.remember_user(from_id, name=from_name)
            room_id = data.get('room_id')
            if room_id:
                self.pending_invitations[room_id] = data
            print(f"[Lobby] 收到來自 {self.resolve_user_display(from_id)} 的邀請 (房間 {data.get('room_id')})。使用 invite/accept/reject 指令處理。")
        elif msg_type == "game_started":
            info = message.get("game_server_info", {})
            room_id = info.get('room_id')
            players = message.get("players", []) or []
            if room_id:
                self.room_members[room_id] = list(players)
            player_names = ", ".join(self.resolve_user_display(uid) for uid in players) if players else "未知"
            print(f"[Lobby] 房間 {room_id or '-'} 正準備開戰：{player_names}")
            self.game_launch_queue.put({"game": info, "players": players, "readOnly": False, "mode": "player", "room_id": room_id})
        elif msg_type == "game_ended":
            results = message.get("results", [])
            print("[Lobby] 對戰結束，結果如下：")
            for line in self.format_match_results(results):
                print(f"  - {line}")
            self.current_room_id = message.get("room_id", self.current_room_id)
        else:
            print(f"[Lobby] Push message: {message}")

    # ---------------- CLI helpers ---------------- #

    def start_cli(self) -> None:
        self.cli_thread = threading.Thread(target=self.cli_loop, daemon=True)
        self.cli_thread.start()

    def cli_loop(self) -> None:
        while self.running:
            if not self.connected_to_lobby:
                if not self.prompt_login_cli():
                    time.sleep(1.0)
                    continue
            try:
                command = input("tetris> ").strip()
            except EOFError:
                self.running = False
                break
            if not command:
                continue
            parts = command.split()
            cmd = parts[0].lower()
            args = parts[1:]
            if cmd in ("quit", "exit"):
                self.running = False
                break
            if cmd == "help":
                self.print_help()
            elif cmd == "rooms":
                self.cmd_list_rooms()
            elif cmd == "create":
                self.cmd_create_room(args)
            elif cmd == "join":
                self.cmd_join_room(args[0] if args else None)
            elif cmd == "leave":
                self.cmd_leave_room()
            elif cmd == "start":
                self.cmd_start_game()
            elif cmd == "online":
                self.cmd_list_online()
            elif cmd == "watch":
                self.cmd_watch(args)
            elif cmd == "invite":
                self.cmd_invite(args)
            elif cmd == "invites":
                self.cmd_list_invitations()
            elif cmd == "accept":
                self.cmd_accept_invite(args)
            elif cmd == "reject":
                self.cmd_reject_invite(args)
            elif cmd == "logout":
                self.logout()
            else:
                print("Unknown command. Type 'help' for list of commands.")
        self.running = False

    def prompt_login_cli(self) -> bool:
        print("\n== Login Menu ==")
        print("1) Login")
        print("2) Register")
        print("3) Quit")
        choice = input("Select option: ").strip()
        if choice == "1":
            email = input("Email: ").strip()
            password = input("Password: ").strip()
            if self.login(email, password):
                self.print_help()
                return True
            return False
        if choice == "2":
            name = input("Display name: ").strip() or "Player"
            email = input("Email: ").strip()
            password = input("Password: ").strip()
            self.register(name, email, password)
            return False
        if choice == "3":
            self.running = False
            return False
        print("Invalid option.")
        return False

    def print_help(self) -> None:
        print("\nCommands:")
        print("  help            Show this message")
        print("  rooms           List public rooms")
        print("  create [public|private] [name]  Create a room with optional visibility")
        print("  join [room_id]  Join a room (omit id to see choices)")
        print("  leave           Leave current room")
        print("  start           Request to start game (needs 2 players)")
        print("  online          List online users")
        print("  watch           Browse and spectate an active match")
        print("  invite <user>   Invite player by name/email/id")
        print("  invites         Show pending invitations")
        print("  accept <room>   Accept invitation by room id")
        print("  reject <room>   Reject invitation by room id")
        print("  logout          Logout from lobby")
        print("  quit            Exit application")

    def cmd_list_rooms(self) -> None:
        rooms = self.fetch_rooms()
        if rooms is None:
            return
        if not rooms:
            print("[Client] No public rooms available.")
            return
        print("\nRooms:")
        for room in rooms:
            rid = room.get("id", "")
            name = room.get("name", "Unnamed")
            status = room.get("status", "idle")
            host_name = room.get("host_name", "Unknown")
            visibility = room.get("visibility", "public")
            vis_label = "Private" if visibility == "private" else "Public"
            users = room.get("users", []) or []
            user_names = room.get("user_names", []) or []
            for uid, uname in zip(users, user_names):
                self.remember_user(uid, name=uname)
            player_labels = ", ".join(user_names) if user_names else "-"
            lock_hint = "(邀請限定)" if visibility == "private" else ""
            print(f"  {rid} | {name} | Host: {host_name} | 型態: {vis_label} {lock_hint} | 狀態: {status} | 玩家: {player_labels}")

    def cmd_create_room(self, args: List[str]) -> None:
        default_name = f"{self.user_name or 'Player'}'s Room"
        visibility = "public"
        name_tokens = list(args)
        if name_tokens:
            candidate = name_tokens[0].lower()
            if candidate in {"public", "private"}:
                visibility = candidate
                name_tokens = name_tokens[1:]
        room_name = " ".join(name_tokens).strip()
        if not room_name:
            room_name = default_name if visibility == "public" else f"{self.user_name or 'Player'}'s Private Room"
        payload = {
            "type": "create_room",
            "data": {"name": room_name, "visibility": visibility},
        }
        response = self.send_request(payload)
        if response and response.get("success"):
            room = response.get("data", {})
            self.current_room_id = room.get("id")
            if self.current_room_id:
                self.room_members[self.current_room_id] = [self.user_id] if self.user_id else []
            print(f"[Client] Created {visibility} room {self.current_room_id} ({room_name}).")
        else:
            error = response.get("error") if response else "no response"
            print(f"[Client] Failed to create room: {error}")

    def cmd_watch(self, args: List[str]) -> None:
        if not self.connected_to_lobby or not self.lobby_handler:
            print("[Client] Please login before using watch.")
            return
        if self.connected_to_game:
            print("[Client] Already connected to a game. Close it before spectating another match.")
            return
        rooms = self.fetch_live_rooms()
        if rooms is None:
            return
        if not rooms:
            print("[Client] No ongoing matches to spectate right now.")
            return

        selection_token: Optional[str] = args[0] if args else None
        chosen_room: Optional[Dict[str, Any]] = None

        if selection_token:
            chosen_room = self.resolve_room_selection(selection_token, rooms)
        else:
            print("\nLive matches:")
            for idx, room in enumerate(rooms, start=1):
                rid = room.get("id", "")
                name = room.get("name", "Unnamed")
                player_names = room.get("playerNames", []) or []
                players_label = ", ".join(player_names) if player_names else "-"
                spectator_count = len(room.get("spectators", []) or [])
                print(f"  {idx}) {rid} | {name} | Players: {players_label} | Spectators: {spectator_count}")
            choice = input("Select match to spectate (number/id, blank to cancel): ").strip()
            if not choice:
                return
            chosen_room = self.resolve_room_selection(choice, rooms)

        if not chosen_room:
            token_desc = selection_token or "selection"
            print(f"[Client] Unable to find a live match matching '{token_desc}'.")
            return

        room_id = chosen_room.get("id")
        if not room_id:
            print("[Client] Invalid room data.")
            return
        self.request_spectate(room_id, chosen_room)

    def resolve_room_selection(self, token: str, rooms: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        token = token.strip()
        if not token:
            return None
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(rooms):
                return rooms[idx]
        for room in rooms:
            rid = room.get("id", "")
            if rid == token or rid.startswith(token):
                return room
        return None

    def request_spectate(self, room_id: str, meta: Optional[Dict[str, Any]] = None) -> None:
        print(f"[Client] Requesting spectate for room {room_id}...")
        response = self.send_request({"type": "spectate_room", "data": {"room_id": room_id}})
        if not response or not response.get("success"):
            error = response.get("error") if response else "no response"
            print(f"[Client] Unable to spectate room {room_id}: {error}")
            return

        data = response.get("data", {}) or {}
        game_info = data.get("game_server_info", {}) or {}
        if not game_info:
            print("[Client] Lobby response missing game server info.")
            return
        game_info.setdefault("mode", "spectator")

        players = data.get("players", []) or []
        player_names = data.get("playerNames", []) or []
        if meta:
            players = meta.get("players", players) or players
            player_names = meta.get("playerNames", player_names) or player_names

        for uid, uname in zip(players, player_names):
            self.remember_user(uid, name=uname)

        payload = {
            "game": game_info,
            "players": players,
            "playerNames": player_names,
            "readOnly": data.get("readOnly", True),
            "mode": "spectator",
            "room_id": room_id
        }
        self.game_launch_queue.put(payload)
        print(f"[Client] Starting spectate session for room {room_id}.")

    def notify_stop_spectate(self) -> None:
        if not self.spectating_room_id:
            return
        if not self.connected_to_lobby or not self.lobby_handler:
            self.spectating_room_id = None
            return
        payload = {"type": "stop_spectate", "data": {"room_id": self.spectating_room_id}}
        self.send_request(payload, quiet=True)
        self.spectating_room_id = None

    def cmd_join_room(self, room_id: Optional[str]) -> None:
        if self.current_room_id:
            print("[Client] 已在房間中，請先使用 leave 再加入其他房間。")
            return

        selected_room_id = room_id
        if not selected_room_id:
            rooms = self.fetch_rooms()
            if rooms is None:
                return
            if not rooms:
                print("[Client] 目前沒有任何房間。可使用 create 建立新房間。")
                return

            print("\n可加入的房間:")
            options: List[Tuple[Dict[str, Any], bool]] = []
            joinable_available = False
            for idx, room in enumerate(rooms, start=1):
                rid = room.get("id", "-")
                name = room.get("name", "Unnamed")
                host = room.get("host_name", "Unknown")
                status = room.get("status", "idle")
                players = room.get("user_names", []) or []
                player_labels = ", ".join(players) if players else "-"
                visibility = room.get("visibility", "public")
                join_allowed = bool(room.get("is_joinable_public", room.get("is_open")))
                tag = "Public" if visibility != "private" else "Private"
                join_note = "可加入" if join_allowed else ("需邀請" if visibility == "private" else "不可加入")
                print(f"  {idx}) {rid} | {name} | Host: {host} | 型態: {tag} | 狀態: {status} | 玩家: {player_labels} | {join_note}")
                options.append((room, join_allowed))
                if join_allowed:
                    joinable_available = True

            if not joinable_available:
                print("[Client] 目前沒有可直接加入的公開房間，請使用 create 或等待邀請。")

            choice = input("選擇房間編號或輸入房間ID (Enter 取消): ").strip()
            if not choice:
                print("[Client] 已取消加入動作。")
                return
            if choice.isdigit():
                index = int(choice) - 1
                if index < 0 or index >= len(options):
                    print("[Client] 無效的選項。")
                    return
                selected_room, join_allowed = options[index]
                if not join_allowed:
                    visibility = selected_room.get("visibility", "public")
                    if visibility == "private":
                        print("[Client] 這是私人房間，請等待邀請。")
                    else:
                        print("[Client] 目前無法加入此房間。")
                    return
                selected_room_id = selected_room.get("id")
            else:
                selected_room_id = choice
                match = next((room for room, _ in options if room.get("id") == selected_room_id), None)
                if match:
                    if not match.get("is_joinable_public", match.get("visibility") != "private"):
                        print("[Client] 這是私人房間，請等待邀請。")
                        return

        if not selected_room_id:
            print("[Client] 房間代號無效。")
            return

        payload = {"type": "join_room", "data": {"room_id": selected_room_id}}
        response = self.send_request(payload)
        if response and response.get("success"):
            joined_room_id = self.handle_join_success(selected_room_id, response)
            print(f"[Client] Joined room {joined_room_id or selected_room_id}.")
        else:
            error = response.get("error") if response else "no response"
            print(f"[Client] Failed to join room: {error}")

    def cmd_leave_room(self) -> None:
        # 離開房間：向 Lobby 發 leave_room，並清理本地 room_members 與 current_room_id
        # 輸入: 無。副作用: 重設 current_room_id 與移除 room_members。
        room_id = self.current_room_id
        response = self.send_request({"type": "leave_room", "data": {}}, quiet=True)
        if not response:
            print("[Client] Unable to leave room (連線中斷或逾時)。")
            return
        if response.get("success"):
            print("[Client] Left room.")
            if room_id:
                self.room_members.pop(room_id, None)
            self.current_room_id = None
            return
        error = response.get("error", "Unknown error")
        if error == "Not in a room":
            print("[Client] 已不在任何房間。")
            self.current_room_id = None
            if room_id:
                self.room_members.pop(room_id, None)
        else:
            print(f"[Client] Unable to leave room: {error}")

    def cmd_start_game(self) -> None:
        # 請求房內開始遊戲（需 2 人）：向 Lobby 發 start_game 請求並顯示結果
        # 輸入: 無。副作用: 可能觸發 Lobby 啟動 game server。
        response = self.send_request({"type": "start_game", "data": {}}, quiet=True)
        if response and response.get("success"):
            print("[Client] Start game request accepted. Waiting for match...")
        else:
            error = response.get("error") if response else "no response"
            print(f"[Client] Cannot start game: {error}")

    def cmd_list_online(self) -> None:
        # 列出線上使用者：請求 Lobby 的 list_online_users 並格式化輸出
        # 輸入: 無。副作用: 印出線上使用者清單。
        response = self.send_request({"type": "list_online_users", "data": {}}, quiet=True)
        if not response or not response.get("success"):
            print("[Client] Failed to list online users.")
            return
        users = response.get("data", [])
        print("\nOnline users:")
        for user in users:
            status = "online" if user.get("online") else "offline"
            if user.get("in_room"):
                status += " (in room)"
            marker = "*" if user.get("user_id") == self.user_id else "-"
            print(f"  {marker} {user.get('name')} <{user.get('email')}> [{status}]")

    def cmd_invite(self, args: List[str]) -> None:
        # 發送邀請給線上玩家：解析候選並呼叫 Lobby 的 invite
        # 輸入: args 指定目標標識。副作用: 可能更新 pending invitations 與通知目標使用者。
        if not self.current_room_id:
            print("[Client] 尚未在房間中，無法發送邀請。")
            return
        if not args:
            print("Usage: invite <email|name|user_id>")
            return

        identifier = " ".join(args).strip()
        candidates = self.find_online_user_candidates(identifier)
        if not candidates:
            print(f"[Client] 找不到符合 \"{identifier}\" 的線上玩家。")
            return

        target = None
        if len(candidates) == 1:
            target = candidates[0]
        else:
            print("[Client] 找到多名符合的線上玩家：")
            for idx, user in enumerate(candidates, start=1):
                status = "in room" if user.get("in_room") else "available"
                print(f"  {idx}) {user.get('name')} <{user.get('email')}> ({user.get('user_id')}) [{status}]")
            choice = input("選擇欲邀請的玩家編號 (Enter 取消): ").strip()
            if not choice:
                print("[Client] 已取消邀請。")
                return
            if not choice.isdigit():
                print("[Client] 無效的選項。")
                return
            index = int(choice) - 1
            if index < 0 or index >= len(candidates):
                print("[Client] 選項超出範圍。")
                return
            target = candidates[index]

        if not target:
            print("[Client] 無法辨識要邀請的玩家。")
            return
        if target.get("user_id") == self.user_id:
            print("[Client] 無法邀請自己。")
            return
        if target.get("in_room"):
            print("[Client] 該玩家目前已在其他房間。")
            return

        target_id = target.get("user_id")
        if not target_id:
            print("[Client] 該玩家資料不完整，無法發送邀請。")
            return

        self.remember_user(target_id, name=target.get("name"), email=target.get("email"))
        payload = {"type": "invite", "data": {"target_user_id": target_id}}
        response = self.send_request(payload, quiet=True)
        if response and response.get("success"):
            print(f"[Client] 已向 {self.resolve_user_display(target_id)} 發送邀請。")
        else:
            error = response.get("error") if response else "no response"
            print(f"[Client] 無法發送邀請: {error}")

    def cmd_list_invitations(self) -> None:
        invites = self.fetch_invitations()
        if not invites:
            print("[Client] 目前沒有待處理的邀請。")
            return
        print("\n待處理邀請：")
        for idx, invitation in enumerate(invites, start=1):
            print(f"  {idx}) {self.format_invitation_summary(invitation)}")

    def cmd_accept_invite(self, args: List[str]) -> None:
        if self.current_room_id:
            print("[Client] 已經在房間中，請先離開目前房間再接受邀請。")
            return

        invites = self.fetch_invitations(quiet=True)
        if not invites:
            print("[Client] 目前沒有可接受的邀請。")
            return

        token = args[0] if args else None
        invitation, cancelled = self.select_invitation(invites, token, "接受")
        if not invitation:
            if token and not cancelled:
                print(f"[Client] 找不到符合房間 {token} 的邀請。")
            return

        room_id = invitation.get("room_id")
        response = self.send_request({"type": "accept_invite", "data": {"room_id": room_id}}, quiet=True)
        if response and response.get("success"):
            joined_room_id = self.handle_join_success(room_id, response)
            print(f"[Client] 已接受邀請並加入房間 {joined_room_id or room_id}。")
            if room_id:
                self.pending_invitations.pop(room_id, None)
        else:
            error = response.get("error") if response else "no response"
            print(f"[Client] 無法接受邀請: {error}")

    def cmd_reject_invite(self, args: List[str]) -> None:
        invites = self.fetch_invitations(quiet=True)
        if not invites:
            print("[Client] 目前沒有可拒絕的邀請。")
            return

        token = args[0] if args else None
        invitation, cancelled = self.select_invitation(invites, token, "拒絕")
        if not invitation:
            if token and not cancelled:
                print(f"[Client] 找不到符合房間 {token} 的邀請。")
            return

        room_id = invitation.get("room_id")
        response = self.send_request({"type": "reject_invite", "data": {"room_id": room_id}}, quiet=True)
        if response and response.get("success"):
            print(f"[Client] 已拒絕房間 {room_id} 的邀請。")
            if room_id:
                self.pending_invitations.pop(room_id, None)
        else:
            error = response.get("error") if response else "no response"
            print(f"[Client] 無法拒絕邀請: {error}")

    # ---------------- Game session ---------------- #

    def start_game_session(self, info: Dict[str, Any]) -> None:
        players = info.get("players", []) or []
        player_names = info.get("playerNames", []) or []
        for uid, uname in zip(players, player_names):
            self.remember_user(uid, name=uname)

        self.read_only = bool(info.get("readOnly", False))
        room_id = info.get("room_id")
        if self.read_only:
            self.spectating_room_id = room_id
        else:
            self.spectating_room_id = None

        with self.game_state_lock:
            self.player_slots = list(players)
            if self.read_only:
                self.primary_player_id = players[0] if players else None
                self.secondary_player_id = players[1] if len(players) > 1 else None
            else:
                if self.user_id and self.user_id in players:
                    self.primary_player_id = self.user_id
                    self.secondary_player_id = next((uid for uid in players if uid != self.user_id), None)
                else:
                    self.primary_player_id = players[0] if players else self.user_id
                    self.secondary_player_id = players[1] if len(players) > 1 else None

        game_info = info.get("game", {})
        if not game_info:
            print("[Client] Invalid game start payload.")
            return
        if not self.connect_to_game(game_info):
            print("[Client] Failed to connect to game server.")
            if self.read_only and self.spectating_room_id:
                self.notify_stop_spectate()
                self.read_only = False
            return
        self.last_line_count = 0
        try:
            self.run_game_loop()
        finally:
            self.disconnect_game()

    def connect_to_game(self, game_info: Dict[str, Any]) -> bool:
        host = game_info.get("host", "localhost")
        port = game_info.get("port")
        room_id = game_info.get("room_id")
        if port is None:
            print("[Client] Game server port missing.")
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((host, port))
            handler = ProtocolHandler(sock)
            hello = {
                "type": "HELLO",
                "userId": self.user_id,
                "roomId": room_id,
                "version": 1,
            }
            mode = game_info.get("mode") or ("spectator" if self.read_only else "player")
            if mode:
                hello["mode"] = mode
            handler.send_message(hello)
            response = handler.receive_message()
            if not response or response.get("type") != "WELCOME":
                handler.close()
                print(f"[Client] Unexpected game handshake: {response}")
                return False
            try:
                handler.sock.settimeout(None)
            except Exception:  # noqa: BLE001
                pass
            self.game_handler = handler
            self.connected_to_game = True
            self.role = response.get("role")
            with self.game_state_lock:
                self.game_started_at = None
                self.game_results = None
                self.round_duration = 90.0
                if response.get("readOnly") is True:
                    self.read_only = True
            threading.Thread(target=self.game_receive_loop, daemon=True).start()
            print(f"[Client] Connected to game server as {self.role}.")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[Client] Game connect error: {exc}")
            return False

    def disconnect_game(self) -> None:
        self.connected_to_game = False
        if self.game_handler:
            try:
                self.game_handler.close()
            except Exception:  # noqa: BLE001
                pass
        self.game_handler = None
        self.role = None
        if self.read_only and self.spectating_room_id:
            self.notify_stop_spectate()
        with self.game_state_lock:
            self.player_slots = []
            self.primary_player_id = None
            self.secondary_player_id = None
            self.game_started_at = None
            self.round_duration = 90.0
        if self.read_only:
            self.read_only = False
        else:
            self.spectating_room_id = None

    def game_receive_loop(self) -> None:
        handler = self.game_handler
        if not handler:
            return
        while self.connected_to_game:
            try:
                message = handler.receive_message()
                if not message:
                    print("[Client] Game connection closed by server.")
                    break
                self.handle_game_message(message)
            except Exception as exc:  # noqa: BLE001
                print(f"[Client] Game listener error: {exc}")
                break
        self.connected_to_game = False

    def handle_game_message(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "GAME_START":
            now = time.time()
            server_ts = message.get("timestamp")
            if isinstance(server_ts, (int, float)) and server_ts > 0:
                # Use server timestamp when available while clamping to now to avoid negative elapsed time.
                start_time = min(now, float(server_ts))
            else:
                start_time = now
            duration = message.get("roundDuration")
            round_duration = self.round_duration
            if isinstance(duration, (int, float)) and duration > 0:
                round_duration = float(duration)
            players = message.get("players", []) or []
            with self.game_state_lock:
                self.game_started_at = start_time
                self.round_duration = round_duration
                if players:
                    self.player_slots = list(players)
                    if self.read_only:
                        self.primary_player_id = players[0] if players else self.primary_player_id
                        self.secondary_player_id = players[1] if len(players) > 1 else self.secondary_player_id
                    elif self.user_id and self.user_id in players:
                        self.primary_player_id = self.user_id
                        self.secondary_player_id = next((uid for uid in players if uid != self.user_id), None)
            print("[Game] Match started.")
        elif msg_type == "SNAPSHOT":
            user_id = message.get("userId")
            with self.game_state_lock:
                if user_id and user_id not in self.player_slots:
                    self.player_slots.append(user_id)
                if self.read_only:
                    if not self.primary_player_id:
                        self.primary_player_id = user_id
                    if user_id == self.primary_player_id:
                        self.update_my_state(message)
                    else:
                        if not self.secondary_player_id:
                            self.secondary_player_id = user_id
                        if user_id == self.secondary_player_id:
                            self.update_opp_state(message)
                else:
                    if user_id == self.primary_player_id or user_id == self.user_id:
                        self.primary_player_id = self.user_id or user_id
                        self.update_my_state(message)
                    else:
                        if not self.secondary_player_id:
                            self.secondary_player_id = user_id
                        if user_id == self.secondary_player_id:
                            self.update_opp_state(message)
        elif msg_type == "GAME_END":
            with self.game_state_lock:
                self.game_results = message
                self.game_started_at = None
                self.round_duration = 90.0
                self.player_slots = []
                self.primary_player_id = None
                self.secondary_player_id = None
            self.connected_to_game = False
            print("[Game] Match finished.")

    def update_my_state(self, snapshot: Dict[str, Any]) -> None:
        previous_lines = self.my_state.get("lines", 0)
        self.my_board = self.extract_board(snapshot)
        self.my_state.update({
            "score": snapshot.get("score", 0),
            "lines": snapshot.get("lines", 0),
            "level": snapshot.get("level", 1),
            "next": snapshot.get("next", []),
            "hold": snapshot.get("hold"),
            "current": (snapshot.get("active") or {}).get("shape"),
            "x": (snapshot.get("active") or {}).get("x", 0),
            "y": (snapshot.get("active") or {}).get("y", 0),
            "rot": (snapshot.get("active") or {}).get("rot", 0),
        })
        new_lines = self.my_state.get("lines", 0)
        if new_lines > max(previous_lines, self.last_line_count):
            self.play_sound("line_clear")
            self.effects["line_flash"] = time.time()
        self.last_line_count = new_lines

    def update_opp_state(self, snapshot: Dict[str, Any]) -> None:
        self.opp_board = self.extract_board(snapshot)
        self.opp_state.update({
            "score": snapshot.get("score", 0),
            "lines": snapshot.get("lines", 0),
            "level": snapshot.get("level", 1),
            "current": (snapshot.get("active") or {}).get("shape"),
            "x": (snapshot.get("active") or {}).get("x", 0),
            "y": (snapshot.get("active") or {}).get("y", 0),
            "rot": (snapshot.get("active") or {}).get("rot", 0),
        })

    def extract_board(self, snapshot: Dict[str, Any]) -> List[List[int]]:
        matrix = snapshot.get("boardMatrix")
        if matrix:
            try:
                return [list(row[:10]) for row in matrix[:20]]
            except Exception:  # noqa: BLE001
                pass
        return self.decode_board_rle(snapshot.get("boardRLE", ""))

    def decode_board_rle(self, rle: str) -> List[List[int]]:
        if not rle:
            return [[0 for _ in range(10)] for _ in range(20)]
        flat: List[int] = []
        i = 0
        length = len(rle)
        while i < length:
            count_str = ""
            while i < length and rle[i].isdigit():
                count_str += rle[i]
                i += 1
            if count_str and i < length and rle[i].isdigit():
                count = int(count_str)
                value = int(rle[i])
                flat.extend([value] * count)
                i += 1
            elif i < length and rle[i].isdigit():
                flat.append(int(rle[i]))
                i += 1
            else:
                i += 1
        total = 200
        if len(flat) < total:
            flat.extend([0] * (total - len(flat)))
        elif len(flat) > total:
            flat = flat[:total]
        board = []
        for row in range(20):
            start = row * 10
            board.append(flat[start:start + 10])
        return board

    def run_game_loop(self) -> None:
        pygame.mixer.pre_init(44100, -16, 1, 256)
        pygame.init()
        screen = pygame.display.set_mode((900, 720))
        pygame.display.set_caption("Tetris Battle")
        clock = pygame.time.Clock()
        font = pygame.font.SysFont("consolas", 22)
        small_font = pygame.font.SysFont("consolas", 18)
        if not self.read_only:
            self.prepare_game_audio()

        while self.running and self.connected_to_game:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.send_leave_game()
                    self.connected_to_game = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.send_leave_game()
                        self.connected_to_game = False
                    else:
                        if self.read_only:
                            continue
                        action = INPUT_MAPPING.get(event.key)
                        if action:
                            self.send_input(action)
            screen.fill((18, 18, 28))
            with self.game_state_lock:
                my_board = [row[:] for row in self.my_board]
                opp_board = [row[:] for row in self.opp_board]
                my_state = dict(self.my_state)
                opp_state = dict(self.opp_state)
                started_at = self.game_started_at
                round_duration = self.round_duration
                primary_id = self.primary_player_id
                secondary_id = self.secondary_player_id
                player_slots = list(self.player_slots)
                read_only = self.read_only
            self.draw_game(
                screen,
                font,
                small_font,
                my_board,
                opp_board,
                my_state,
                opp_state,
                started_at,
                round_duration,
                read_only,
                primary_id,
                secondary_id,
                player_slots,
            )
            pygame.display.flip()
            clock.tick(60)
        pygame.display.quit()
        pygame.quit()
        if self.game_results:
            print("[Game] Results:")
            results = self.game_results.get("results", []) or []
            formatted = self.format_match_results(results)
            for line in formatted:
                print(f"  - {line}")

    def send_input(self, action: str) -> None:
        if self.connected_to_game and self.game_handler:
            payload = {
                "type": "INPUT",
                "userId": self.user_id,
                "seq": int(time.time() * 1000),
                "ts": int(time.time() * 1000),
                "action": action,
            }
            try:
                self.game_handler.send_message(payload)
            except Exception as exc:  # noqa: BLE001
                print(f"[Client] Failed to send input: {exc}")
            else:
                if action == "HARD_DROP":
                    self.play_sound("hard_drop")
                    self.effects["hard_drop"] = time.time()

    def send_leave_game(self) -> None:
        if self.connected_to_game and self.game_handler:
            try:
                self.game_handler.send_message({
                    "type": "LEAVE_GAME",
                    "userId": self.user_id,
                    "ts": int(time.time() * 1000),
                })
            except Exception:  # noqa: BLE001
                pass

    def draw_game(self, screen: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font,
                  my_board: List[List[int]], opp_board: List[List[int]],
                  my_state: Dict[str, Any], opp_state: Dict[str, Any], started_at: Optional[float],
                  round_duration: float, read_only: bool, primary_id: Optional[str],
                  secondary_id: Optional[str], player_slots: List[str]) -> None:
        board_x = 120
        board_y = 80
        cell_size = 26
        opp_x = 560
        opp_y = 160
        opp_cell = 18

        pygame.draw.rect(screen, (32, 36, 54), pygame.Rect(80, 40, 340, 620), 0, 14)
        pygame.draw.rect(screen, (26, 28, 40), pygame.Rect(82, 42, 336, 616), 2, 14)
        pygame.draw.rect(screen, (42, 46, 66), pygame.Rect(520, 140, 280, 420), 0, 12)

        self.draw_board(screen, my_board, board_x, board_y, cell_size)
        self.draw_board(screen, opp_board, opp_x, opp_y, opp_cell)
        self.draw_active_piece(screen, my_state, board_x, board_y, cell_size)
        self.draw_active_piece(screen, opp_state, opp_x, opp_y, opp_cell)
        self.draw_board_effects(screen, board_x, board_y, cell_size)

        if read_only:
            title_text = "Tetris Battle - Spectating"
        else:
            title_text = f"Tetris Battle - {self.user_name}"
        title = font.render(title_text, True, (220, 220, 240))
        screen.blit(title, (board_x, 20))
        self.draw_info_panel(
            screen,
            font,
            small_font,
            my_state,
            opp_state,
            started_at,
            round_duration,
            read_only,
            primary_id,
            secondary_id,
            player_slots,
        )

        hint_text = "Esc: leave spectate" if read_only else "Esc: leave game"
        hint = small_font.render(hint_text, True, (160, 160, 160))
        screen.blit(hint, (520, 520))

    def draw_board(self, screen: pygame.Surface, board: List[List[int]], x: int, y: int, cell: int) -> None:
        bg = pygame.Surface((10 * cell, 20 * cell))
        bg.fill((25, 25, 38))
        screen.blit(bg, (x - 2, y - 2))
        for row in range(20):
            for col in range(10):
                value = board[row][col]
                color = COLORS.get(value, (40, 40, 60))
                rect = pygame.Rect(x + col * cell, y + row * cell, cell - 1, cell - 1)
                pygame.draw.rect(screen, color, rect)
        border_rect = pygame.Rect(x - 2, y - 2, 10 * cell + 4, 20 * cell + 4)
        pygame.draw.rect(screen, (200, 200, 220), border_rect, 2)

    def draw_active_piece(self, screen: pygame.Surface, state: Dict[str, Any], base_x: int, base_y: int, cell: int) -> None:
        piece = state.get("current")
        if not piece or piece not in SHAPES:
            return
        rotation = state.get("rot", 0)
        shape = self.rotate_shape(SHAPES[piece], rotation)
        offset_x = state.get("x", 0)
        offset_y = state.get("y", 0)
        color_value = list(SHAPES.keys()).index(piece) + 1
        color = COLORS.get(color_value, (255, 255, 255))
        for r, row in enumerate(shape):
            for c, cell_value in enumerate(row):
                if cell_value:
                    rect = pygame.Rect(
                        base_x + (offset_x + c) * cell,
                        base_y + (offset_y + r) * cell,
                        cell - 1,
                        cell - 1,
                    )
                    pygame.draw.rect(screen, color, rect)

    def draw_info_panel(self, screen: pygame.Surface, font: pygame.font.Font,
                        small_font: pygame.font.Font, my_state: Dict[str, Any],
                        opp_state: Dict[str, Any], started_at: Optional[float],
                        round_duration: float, read_only: bool,
                        primary_id: Optional[str], secondary_id: Optional[str],
                        player_slots: List[str]) -> None:
        panel_rect = pygame.Rect(520, 60, 320, 120)
        pygame.draw.rect(screen, (24, 28, 48), panel_rect, border_radius=12)
        pygame.draw.rect(screen, (95, 112, 165), panel_rect, 2, border_radius=12)

        my_score = my_state.get('score', 0)
        my_lines = my_state.get('lines', 0)
        opp_lines = opp_state.get('lines', 0)
        level = my_state.get('level', 1)

        def name_for(uid: Optional[str], fallback_index: int) -> str:
            if uid:
                return self.resolve_user_display(uid)
            if 0 <= fallback_index < len(player_slots):
                return self.resolve_user_display(player_slots[fallback_index])
            return "Player" if fallback_index == 0 else "Opponent"

        my_label_text = "You" if not read_only else name_for(primary_id, 0)
        opp_label_text = name_for(secondary_id, 1)

        score_surface = font.render(f"Score {my_score:>6}", True, (255, 214, 130))
        lines_surface = font.render(f"Lines {my_lines:>6}", True, (200, 230, 255))
        level_surface = small_font.render(f"Level {level}", True, (185, 200, 240))
        my_label_surface = small_font.render(my_label_text, True, (255, 214, 130))
        opp_label_surface = small_font.render(opp_label_text, True, (170, 200, 255))
        opp_lines_surface = font.render(f"Lines {opp_lines:>6}", True, (170, 200, 255))

        y_offset = panel_rect.y + 10
        screen.blit(my_label_surface, (panel_rect.x + 16, y_offset))
        y_offset += my_label_surface.get_height() + 2
        screen.blit(score_surface, (panel_rect.x + 16, y_offset))
        y_offset += score_surface.get_height()
        screen.blit(lines_surface, (panel_rect.x + 16, y_offset))
        y_offset += lines_surface.get_height()
        screen.blit(level_surface, (panel_rect.x + 16, y_offset + 4))

        opp_y = panel_rect.y + 10
        screen.blit(opp_label_surface, (panel_rect.x + 180, opp_y))
        opp_y += opp_label_surface.get_height() + 2
        screen.blit(opp_lines_surface, (panel_rect.x + 180, opp_y))

        if started_at:
            elapsed = max(0.0, time.time() - started_at)
            if round_duration > 0:
                remaining = max(0.0, round_duration - elapsed)
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                tenths = int((remaining - int(remaining)) * 10)
                timer_label = "Time left"
            else:
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                tenths = int((elapsed - int(elapsed)) * 10)
                timer_label = "Time"
            timer_text = font.render(f"{timer_label} {mins:02d}:{secs:02d}.{tenths}", True, (255, 245, 200))
            screen.blit(timer_text, (panel_rect.x + 150, panel_rect.y + 62))

    def rotate_shape(self, shape: List[List[int]], rotation: int) -> List[List[int]]:
        rotated = [row[:] for row in shape]
        for _ in range(rotation % 4):
            rotated = [list(row) for row in zip(*rotated[::-1])]
        return rotated

    def prepare_game_audio(self) -> None:
        if self.audio_ready:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=1)
        except Exception as exc:  # noqa: BLE001
            print(f"[Client] Audio init failed: {exc}")
            return
        self.sound_effects["hard_drop"] = self.generate_tone(880, 70, volume=0.6)
        self.sound_effects["line_clear"] = self.generate_tone(523, 140, volume=0.7)
        self.audio_ready = True

    def generate_tone(self, frequency: int, duration_ms: int, *, volume: float = 0.5,
                      sample_rate: int = 44100) -> Optional[pygame.mixer.Sound]:
        try:
            amplitude = int(32767 * max(0.0, min(volume, 1.0)))
            n_samples = int(sample_rate * duration_ms / 1000)
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                frame_bytes = bytearray()
                for i in range(n_samples):
                    sample = int(amplitude * math.sin(2 * math.pi * frequency * (i / sample_rate)))
                    frame_bytes.extend(struct.pack('<h', sample))
                wav_file.writeframes(frame_bytes)
            buffer.seek(0)
            return pygame.mixer.Sound(buffer=buffer.read())
        except Exception as exc:  # noqa: BLE001
            print(f"[Client] Failed to generate tone: {exc}")
            return None

    def play_sound(self, name: str) -> None:
        if not self.audio_ready:
            return
        sound = self.sound_effects.get(name)
        if not sound:
            return
        try:
            sound.play()
        except Exception:  # noqa: BLE001
            pass

    def force_leave_room(self) -> None:
        if not self.connected_to_lobby or not self.current_room_id:
            return
        response = self.send_request({"type": "leave_room", "data": {}}, quiet=True)
        if response and response.get("success"):
            self.current_room_id = None

    def draw_board_effects(self, screen: pygame.Surface, board_x: int, board_y: int, cell_size: int) -> None:
        now = time.time()
        width = 10 * cell_size
        height = 20 * cell_size
        rect_pos = (board_x, board_y)

        hard_elapsed = now - self.effects.get("hard_drop", 0.0)
        if 0.0 <= hard_elapsed < 0.35:
            intensity = max(0.0, 1.0 - hard_elapsed / 0.35)
            overlay = pygame.Surface((width, height), pygame.SRCALPHA)
            color = (200, 240, 255, int(110 * intensity))
            overlay.fill(color)
            screen.blit(overlay, rect_pos)
            glow = pygame.Surface((width, height), pygame.SRCALPHA)
            pygame.draw.rect(glow, (255, 255, 255, int(160 * intensity)), glow.get_rect(), width=4)
            screen.blit(glow, rect_pos)

        line_elapsed = now - self.effects.get("line_flash", 0.0)
        if 0.0 <= line_elapsed < 0.6:
            pulse = max(0.0, 1.0 - line_elapsed / 0.6)
            ring = pygame.Surface((width, height), pygame.SRCALPHA)
            alpha = int(180 * (pulse ** 1.5))
            pygame.draw.rect(ring, (255, 220, 120, alpha), ring.get_rect(), width=6)
            screen.blit(ring, rect_pos)

    # ---------------- Main loop ---------------- #

    def run(self) -> None:
        self.start_cli()
        try:
            while self.running:
                try:
                    payload = self.game_launch_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if not self.running:
                    break
                if self.connected_to_game:
                    print("[Client] Already in a game, ignoring new start signal.")
                    continue
                self.start_game_session(payload)
        except KeyboardInterrupt:
            print("\n[Client] Interrupted, shutting down.")
            self.running = False
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        self.running = False
        self.send_leave_game()
        self.disconnect_game()
        self.force_leave_room()
        self.logout()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simplified Tetris game client")
    parser.add_argument("--lobby-host", default="localhost", help="Lobby server host")
    parser.add_argument("--lobby-port", type=int, default=10002, help="Lobby server port")
    args = parser.parse_args()

    client = GameClient(args.lobby_host, args.lobby_port)
    client.run()


if __name__ == "__main__":
    main()
