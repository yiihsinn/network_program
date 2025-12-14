#!/usr/bin/env python3
"""
Game Server - 俄羅斯方塊遊戲伺服器
處理遊戲邏輯、狀態同步、計分等
"""

import socket
import threading
import time
import random
import json
from typing import Dict, Any, List, Optional, Tuple
from protocol import ProtocolHandler
from datetime import datetime

# 俄羅斯方塊形狀定義
TETROMINOS = {
    'I': {'shape': [[1,1,1,1]], 'color': 'cyan'},
    'O': {'shape': [[1,1],[1,1]], 'color': 'yellow'},
    'T': {'shape': [[0,1,0],[1,1,1]], 'color': 'purple'},
    'S': {'shape': [[0,1,1],[1,1,0]], 'color': 'green'},
    'Z': {'shape': [[1,1,0],[0,1,1]], 'color': 'red'},
    'J': {'shape': [[1,0,0],[1,1,1]], 'color': 'blue'},
    'L': {'shape': [[0,0,1],[1,1,1]], 'color': 'orange'}
}

class TetrisGame:
    """單個玩家的俄羅斯方塊遊戲狀態"""
    
    def __init__(self, user_id: str, seed: int):
        self.user_id = user_id
        self.board = [[0 for _ in range(10)] for _ in range(20)]  # 10x20 棋盤
        self.lines = 0
        self.level = 1
        self.game_over = False
        
        # 當前方塊
        self.current_piece = None
        self.current_x = 4
        self.current_y = 0
        self.current_rotation = 0
        
        # 下一個方塊序列（7-bag system）
        self.bag = []
        self.next_pieces = []
        self.random = random.Random(seed)
        self.refill_bag()
        
        # Hold 功能
        self.hold_piece = None
        self.can_hold = True
        
        # 時間控制
        self.last_drop_time = time.time()
        self.drop_interval = 1.0  # 初始每秒下降一格
        # 行消除動畫支持
        self.clearing_rows = []
        self.clear_effect_start = None
        self.clear_effect_delay = 0.35  # 秒，延遲後再真正移除
        
    def refill_bag(self):
        # 填充方塊袋：使用 7-bag 與 Fisher-Yates 洗牌，確保 next_pieces 維持足夠預覽。
        # 輸入: 無，副作用: 修改 self.bag 與 self.next_pieces。
        """填充方塊袋（7-bag system with Fisher-Yates shuffle）"""
        pieces = list(TETROMINOS.keys())
        # Fisher-Yates shuffle
        for i in range(len(pieces) - 1, 0, -1):
            j = self.random.randint(0, i)
            pieces[i], pieces[j] = pieces[j], pieces[i]
        self.bag.extend(pieces)
        
        # 確保有足夠的預覽方塊
        while len(self.next_pieces) < 3:
            if not self.bag:
                self.refill_bag()
            self.next_pieces.append(self.bag.pop(0))
    
    def spawn_piece(self):
        # 生成新方塊：從 next_pieces 取得下一個方塊並重置位子/旋轉，檢查是否造成遊戲結束。
        # 回傳: True 表示成功產生新方塊；False 表示產生時發生碰撞導致遊戲結束。
        """生成新方塊"""
        if not self.next_pieces:
            self.refill_bag()
        
        self.current_piece = self.next_pieces.pop(0)
        self.current_x = 4
        self.current_y = 0
        self.current_rotation = 0
        self.can_hold = True
        
        self.refill_bag()
        
        # 檢查是否遊戲結束
        if self.check_collision():
            self.game_over = True
            return False
        return True
    
    def rotate_matrix(self, matrix: List[List[int]], clockwise: bool = True) -> List[List[int]]:
        # 矩陣旋轉工具：對方塊形狀做順/逆時鐘旋轉，回傳新的矩陣。
        # 輸入: matrix, clockwise。輸出: 旋轉後的矩陣。
        """旋轉矩陣"""
        if clockwise:
            return [list(row) for row in zip(*matrix[::-1])]
        else:
            return [list(row) for row in zip(*matrix)][::-1]
    
    def get_current_shape(self) -> List[List[int]]:
        # 取得當前方塊經過 rotation 轉換後的形狀矩陣；若無 current_piece 回傳空列表。
        """取得當前方塊形狀"""
        if not self.current_piece:
            return []
        
        shape = TETROMINOS[self.current_piece]['shape']
        for _ in range(self.current_rotation):
            shape = self.rotate_matrix(shape)
        return shape
    
    def check_collision(self, dx: int = 0, dy: int = 0, rotation: int = None) -> bool:
        # 檢查碰撞：模擬方塊移動/旋轉後是否會與牆或已放置方塊發生碰撞。
        # 輸入: dx, dy, rotation。輸出: 布林，True 表示會碰撞。
        """檢查碰撞"""
        if not self.current_piece:
            return False
        
        if rotation is None:
            shape = self.get_current_shape()
        else:
            shape = TETROMINOS[self.current_piece]['shape']
            for _ in range(rotation):
                shape = self.rotate_matrix(shape)
        
        new_x = self.current_x + dx
        new_y = self.current_y + dy
        
        for row_idx, row in enumerate(shape):
            for col_idx, cell in enumerate(row):
                if cell:
                    board_x = new_x + col_idx
                    board_y = new_y + row_idx
                    
                    # 邊界檢查
                    if board_x < 0 or board_x >= 10 or board_y >= 20:
                        return True
                    
                    # 已放置方塊檢查
                    if board_y >= 0 and self.board[board_y][board_x]:
                        return True
        
        return False
    
    def lock_piece(self):
        # 鎖定當前方塊：把 active piece 寫入 board，觸發行清除流程或直接 spawn 新方塊。
        # 副作用: 修改 self.board、可能設置 clearing_rows 或 spawn 新方塊。
        """鎖定當前方塊"""
        shape = self.get_current_shape()
        color_value = list(TETROMINOS.keys()).index(self.current_piece) + 1
        
        for row_idx, row in enumerate(shape):
            for col_idx, cell in enumerate(row):
                if cell:
                    board_y = self.current_y + row_idx
                    board_x = self.current_x + col_idx
                    if 0 <= board_y < 20:
                        self.board[board_y][board_x] = color_value
        
        # 嘗試觸發行清除動畫（延遲真正移除）
        self.clear_lines()
        # 若有清除動畫，暫時移除 active piece，保留其落地方塊在 board 中，等待動畫完成後再產生新方塊
        if self.clearing_rows:
            # 讓快照中的 active 變成 None，避免使用者誤以為仍可控制；鎖定方塊仍在 board 上保持可見
            self.current_piece = None
        else:
            # 沒有行清除立即生成新方塊
            self.spawn_piece()
    
    def clear_lines(self):
        # 偵測並標記完整行以啟動清除動畫，實際移除與計分在 finalize_line_clear 中處理。
        # 副作用: 設定 self.clearing_rows 與 clear_effect_start。
        """清除完整的行"""
        if self.clearing_rows and self.clear_effect_start:
            # 已經在動畫過程中，不重複觸發
            return
        full_rows = []
        for idx, row in enumerate(self.board):
            if all(cell != 0 for cell in row):
                full_rows.append(idx)
        if not full_rows:
            return
        self.clearing_rows = full_rows
        self.clear_effect_start = time.time()
        # 計分與等級改在真正移除時處理

    def finalize_line_clear(self):
        # 完成行清除：在動畫延遲後移除行、計算等級並重建 board。
        # 副作用: 修改 self.board、self.lines、self.level 與 drop_interval。
        """在延遲後真正移除行並更新統計"""
        if not self.clearing_rows:
            return
        if not self.clear_effect_start:
            return
        if time.time() - self.clear_effect_start < self.clear_effect_delay:
            return
        # 進行移除
        remaining = [row[:] for i, row in enumerate(self.board) if i not in self.clearing_rows]
        removed_count = len(self.clearing_rows)
        for _ in range(removed_count):
            remaining.insert(0, [0]*10)
        self.board = remaining
        # 更新統計（移除分數計算）
        self.lines += removed_count
        self.level = (self.lines // 10) + 1
        self.drop_interval = max(0.1, 1.0 - (self.level - 1) * 0.1)
        # 重置動畫狀態
        self.clearing_rows = []
        self.clear_effect_start = None
    
    def move(self, direction: str) -> bool:
        # 移動方塊（左右、下）：嘗試變更位置並處理 soft drop 加分或 lock 動作。
        # 輸入: direction ('left'|'right'|'down')。回傳: 是否有成功變更狀態。
        """移動方塊"""
        if self.game_over or not self.current_piece:
            return False
        
        if direction == 'left':
            if not self.check_collision(dx=-1):
                self.current_x -= 1
                return True
        elif direction == 'right':
            if not self.check_collision(dx=1):
                self.current_x += 1
                return True
        elif direction == 'down':
            if not self.check_collision(dy=1):
                self.current_y += 1
                return True
            else:
                self.lock_piece()
                return True
        
        return False
    
    def rotate(self, clockwise: bool = True) -> bool:
        # 嘗試旋轉方塊並使用簡單的 wall-kick，若成功更新 rotation 與位移。
        # 輸入: clockwise。回傳: 是否旋轉成功。
        """旋轉方塊"""
        if self.game_over or not self.current_piece:
            return False
        
        new_rotation = (self.current_rotation + (1 if clockwise else -1)) % 4
        
        # Wall kick 嘗試
        for kick_x, kick_y in [(0, 0), (-1, 0), (1, 0), (0, -1), (-1, -1), (1, -1)]:
            if not self.check_collision(dx=kick_x, dy=kick_y, rotation=new_rotation):
                self.current_x += kick_x
                self.current_y += kick_y
                self.current_rotation = new_rotation
                return True
        
        return False
    
    def hard_drop(self) -> bool:
        # 硬降：將方塊直接落到最底並鎖定方塊。
        # 回傳: 是否成功執行硬降。
        """硬降（直接落到底）"""
        if self.game_over or not self.current_piece:
            return False
        
        while not self.check_collision(dy=1):
            self.current_y += 1
        
        self.lock_piece()
        return True
    
    def hold(self) -> bool:
        # Hold 功能：交換或儲存當前方塊，並處理首次 hold 的特殊邏輯。
        # 回傳: 是否成功執行 hold。
        """Hold 功能"""
        if self.game_over or not self.current_piece or not self.can_hold:
            return False
        
        if self.hold_piece:
            # 交換
            self.hold_piece, self.current_piece = self.current_piece, self.hold_piece
            self.current_x = 4
            self.current_y = 0
            self.current_rotation = 0
        else:
            # 第一次 hold
            self.hold_piece = self.current_piece
            self.spawn_piece()
        
        self.can_hold = False
        return True
    
    def update(self) -> bool:
        # 周期性更新：處理自動下降、完成行清除與 spawn 新方塊的時序。
        # 回傳: 是否有解造成畫面需要更新（例如方塊下落）。
        """更新遊戲狀態（自動下降）"""
        if self.game_over:
            return False
        # 若有待清除行，嘗試完成清除
        self.finalize_line_clear()
        # 若清除剛完成且目前沒有活動方塊（因為延遲生成），補生成
        if not self.game_over and not self.current_piece and not self.clearing_rows:
            self.spawn_piece()
        
        current_time = time.time()
        if current_time - self.last_drop_time >= self.drop_interval:
            self.move('down')
            self.last_drop_time = current_time
            return True
        
        return False
    
    def get_board_rle(self) -> str:
        # 取得棋盤的簡易 RLE 字串表示，用於快照傳輸時減少大小。
        # 回傳: RLE 字串。
        """取得棋盤的 RLE 壓縮字串"""
        # 簡單的 RLE 壓縮
        flat = []
        for row in self.board:
            for cell in row:
                flat.append(str(cell))
        
        result = []
        i = 0
        while i < len(flat):
            count = 1
            while i + count < len(flat) and flat[i + count] == flat[i]:
                count += 1
            
            if count > 1:
                result.append(f"{count}{flat[i]}")
            else:
                result.append(flat[i])
            i += count
        
        return ''.join(result)

class GameServer:
    # 建構子：初始化 GameServer 狀態 (連接埠、房間、玩家/觀眾結構、同步控制等)
    def __init__(self, port: int, room_id: str, lobby_port: int):
        self.port = port
        self.room_id = room_id
        self.lobby_port = lobby_port
        
        # 玩家管理
        self.players = {}  # {user_id: {handler, game, role}}
        self.spectators = {}  # {user_id: handler}
        # 使用可重入 RLock：允許在持鎖時呼叫需要再取鎖的函式（如 send_snapshot 內也會鎖）。
        # 先前改成普通 Lock 造成 nested locking 死結，導致 GAME_START 後無 snapshot 廣播。
        self.player_lock = threading.RLock()
        
        # 遊戲狀態
        self.game_started = False
        self.game_ended = False
        self.start_time = None
        self.end_time = None
        self.seed = random.randint(0, 2**31 - 1)
        self.round_duration = 90  # seconds
        
        # 同步控制
        self.tick = 0
        self.snapshot_interval = 1.0  # 每秒發送快照
        self.last_snapshot_time = time.time()
        # 調試與診斷
        self.end_reason = None
        self.debug_enabled = True
        
    # 廣播訊息給所有玩家與觀眾（可排除特定 user_id），在鎖內收集收件者再逐一發送。
    def broadcast(self, message: Dict[str, Any], exclude: str = None):
        """廣播訊息給所有玩家與觀眾"""
        with self.player_lock:
            recipients: List[Tuple[str, ProtocolHandler]] = []
            for user_id, player_info in self.players.items():
                handler = player_info.get('handler')
                if handler and user_id != exclude:
                    recipients.append((user_id, handler))
            for user_id, handler in self.spectators.items():
                if handler and user_id != exclude:
                    recipients.append((user_id, handler))

        for uid, handler in recipients:
            try:
                handler.send_message(message)
            except Exception as exc:  # noqa: BLE001
                print(f"[Game][warn] Failed to broadcast to {uid[:6]}: {exc}")
    
    # 處理 HELLO 握手：根據 mode 分配 player 或 spectator，建立遊戲狀態或加入觀眾。
    def handle_hello(self, handler: ProtocolHandler, data: Dict[str, Any]) -> Dict[str, Any]:
        """處理玩家或觀戰者連線"""
        user_id = data.get('userId')
        room_id = data.get('roomId')
        mode = data.get('mode', 'player')

        if room_id != self.room_id:
            return {"type": "ERROR", "error": "Invalid room"}

        if mode == 'spectator':
            with self.player_lock:
                self.spectators[user_id] = handler
            return {
                "type": "WELCOME",
                "role": "SPECTATOR",
                "mode": "spectator",
                "readOnly": True,
                "seed": self.seed,
            }

        with self.player_lock:
            if len(self.players) >= 2:
                return {"type": "ERROR", "error": "Room full"}

            # 分配角色
            role = f"P{len(self.players) + 1}"

            # 建立玩家遊戲狀態
            game = TetrisGame(user_id, self.seed)

            self.players[user_id] = {
                'handler': handler,
                'game': game,
                'role': role
            }

        # 回應 WELCOME
        response = {
            "type": "WELCOME",
            "role": role,
            "mode": "player",
            "readOnly": False,
            "seed": self.seed,
            "bagRule": "7bag",
            "gravityPlan": {"mode": "progressive", "dropMs": 1000}
        }
        # 注意：不在此處啟動遊戲，避免在發送 WELCOME 前廣播 GAME_START
        return response
    
    # 開始比賽：設定 game_started、spawn 初始方塊、廣播 GAME_START，並啟動 game_loop 執行緒。
    def start_game(self):
        """開始遊戲"""
        self.game_started = True
        self.start_time = time.time()
        
        print(f"[Game] Starting game for room {self.room_id}")
        
        # 為每個玩家生成第一個方塊
        with self.player_lock:
            for user_id, player_info in self.players.items():
                game = player_info['game']
                game.spawn_piece()
                print(f"[Game] Spawned first piece for player {user_id}: {game.current_piece}")
        
        # 通知所有玩家遊戲開始
        try:
            self.broadcast({
                "type": "GAME_START",
                "players": list(self.players.keys()),
                "timestamp": self.start_time,
                "roundDuration": self.round_duration
            })
            if self.debug_enabled:
                print(f"[Game][debug] GAME_START broadcasted to {len(self.players)} players")
        except Exception as e:
            print(f"[Game][error] Failed to broadcast GAME_START: {e}")
        
        # 發送初始狀態（使用 RLock 可安全 nested）
        with self.player_lock:
            pending_ids = list(self.players.keys())
        for user_id in pending_ids:
            try:
                self.send_snapshot(user_id)
            except Exception as e:
                print(f"[Game][error] Initial snapshot failed for {user_id}: {e}")
        
        # 啟動遊戲更新執行緒
        thread = threading.Thread(target=self.game_loop)
        thread.daemon = True
        thread.start()
        
        print(f"[Game] Game loop started")
    
    # 處理玩家輸入事件：根據 action 更新玩家的遊戲狀態，成功時回傳 True 並發送快照。
    def handle_input(self, user_id: str, data: Dict[str, Any]) -> bool:
        """處理玩家輸入"""
        if not self.game_started or self.game_ended:
            return False
        
        action = data.get('action')
        
        with self.player_lock:
            if user_id not in self.players:
                return False
            
            game = self.players[user_id]['game']
            
            success = False
            if action == 'LEFT':
                success = game.move('left')
            elif action == 'RIGHT':
                success = game.move('right')
            elif action == 'DOWN':
                success = game.move('down')
            elif action == 'CW':  # Clockwise rotation
                success = game.rotate(True)
            elif action == 'CCW':  # Counter-clockwise rotation
                success = game.rotate(False)
            elif action == 'HARD_DROP':
                success = game.hard_drop()
            elif action == 'HOLD':
                success = game.hold()
            
            if self.debug_enabled:
                try:
                    cx, cy, rot = game.current_x, game.current_y, game.current_rotation
                    print(f"[Game][input] {user_id[:6]} action={action} success={success} pos=({cx},{cy}) rot={rot}")
                except Exception:
                    pass

            # 立即發送更新後的快照
            if success:
                self.send_snapshot(user_id)
            
            return success
    
    # 建構玩家專用快照：將遊戲狀態打包成 dict 用於傳送給該玩家或觀眾。
    def build_snapshot(self, user_id: str) -> Optional[Dict[str, Any]]:
        # 回傳: snapshot dict 或 None（若找不到玩家）。
        with self.player_lock:
            player_info = self.players.get(user_id)
            if not player_info:
                return None
            game = player_info['game']
            snapshot = {
                "type": "SNAPSHOT",
                "tick": self.tick,
                "userId": user_id,
                "boardRLE": game.get_board_rle(),
                "boardMatrix": [row[:] for row in game.board],
                "clearing": game.clearing_rows[:],
                "clearAnim": True if game.clearing_rows else False,
                "active": {
                    "shape": game.current_piece,
                    "x": game.current_x,
                    "y": game.current_y,
                    "rot": game.current_rotation
                } if game.current_piece else None,
                "hold": game.hold_piece,
                "next": game.next_pieces[:3],
                "lines": game.lines,
                "level": game.level,
                "gameOver": game.game_over,
                "at": time.time()
            }
        return snapshot

    # 發送快照：呼叫 build_snapshot 並透過 broadcast 傳送給所有客戶端。
    def send_snapshot(self, user_id: str) -> None:
        snapshot = self.build_snapshot(user_id)
        if not snapshot:
            return
        try:
            self.broadcast(snapshot)
            if self.debug_enabled:
                print(f"[Game][snapshot] uid={user_id[:6]} lines={snapshot['lines']} tick={self.tick}")
        except Exception as e:
            print(f"[Game][error] broadcast snapshot failed for {user_id}: {e}")

    # 在觀戰者連線時，送出 GAME_START (若已開始) 與每位玩家的快照，建立初始觀戰畫面。
    def send_initial_state_to_spectator(self, handler: ProtocolHandler) -> None:
        with self.player_lock:
            player_ids = list(self.players.keys())
            started = self.game_started
            start_time = self.start_time or time.time()
            round_duration = self.round_duration

        if started:
            try:
                handler.send_message({
                    "type": "GAME_START",
                    "players": player_ids,
                    "timestamp": start_time,
                    "roundDuration": round_duration
                })
            except Exception as exc:  # noqa: BLE001
                print(f"[Game][warn] Failed to send GAME_START to spectator: {exc}")

        for pid in player_ids:
            snapshot = self.build_snapshot(pid)
            if not snapshot:
                continue
            try:
                handler.send_message(snapshot)
            except Exception as exc:  # noqa: BLE001
                print(f"[Game][warn] Failed to send snapshot to spectator: {exc}")
    
    # 檢查遊戲結束條件：無玩家超時、所有玩家 game_over、或到達時間上限，回傳是否結束。
    def check_game_end(self) -> bool:
        """檢查遊戲是否結束"""
        with self.player_lock:
            if not self.players:
                # 沒有玩家時不立即結束，等待是否有重連（最多 10 秒），否則標記中止
                if self.start_time and time.time() - self.start_time > 10:
                    self.end_reason = 'aborted_no_players'
                    return True
                return False

            all_game_over = True
            for user_id, player_info in self.players.items():
                if not player_info['game'].game_over:
                    all_game_over = False
            if all_game_over:
                self.end_reason = 'all_players_game_over'
                return True

            if self.start_time and time.time() - self.start_time >= self.round_duration:
                self.end_reason = 'time_limit'
                return True

            return False
    
    # 結束遊戲：收集結果、計算勝者、廣播 GAME_END 並回報給 Lobby。
    def end_game(self):
        """結束遊戲"""
        if self.game_ended:
            return
        
        self.game_ended = True
        self.end_time = time.time()
        
        # 收集結果
        results = []
        
        with self.player_lock:
            for user_id, player_info in self.players.items():
                game = player_info['game']
                # 計算棋盤剩餘方塊數量
                filled_cells = sum(1 for row in game.board for cell in row if cell != 0)
                results.append({
                    "userId": user_id,
                    "lines": game.lines,
                    "level": game.level,
                    "gameOver": game.game_over,
                    "filledCells": filled_cells
                })
        
        # 新勝負判定邏輯：
        # 1. 若只有一人 game_over，另一人獲勝
        # 2. 若都沒 game_over 或都 game_over，比較消行數（多的獲勝）
        # 3. 消行數相同，比較棋盤剩餘方塊數（少的獲勝）
        
        game_over_players = [r for r in results if r['gameOver']]
        not_game_over_players = [r for r in results if not r['gameOver']]
        
        winner_id = None
        
        if len(not_game_over_players) == 1 and len(game_over_players) == 1:
            # 只有一人存活，該玩家獲勝
            winner_id = not_game_over_players[0]['userId']
        else:
            # 比較消行數，再比較剩餘方塊數
            # 排序：先按 lines 降序，再按 filledCells 升序
            results.sort(key=lambda x: (-x['lines'], x['filledCells']))
            winner_id = results[0]['userId']
        
        # 標記獲勝者
        for result in results:
            result['winner'] = (result['userId'] == winner_id)
        
        # 通知玩家
        self.broadcast({
            "type": "GAME_END",
            "results": results,
            "duration": self.end_time - self.start_time,
            "winner": winner_id,
            "reason": self.end_reason or 'unknown'
        })
        
        # 回報給 Lobby
        self.report_to_lobby(results)
    
    # 將遊戲結果透過 TCP 連回 Lobby 伺服器，讓 Lobby 更新房間/比賽狀態。
    def report_to_lobby(self, results: List[Dict[str, Any]]):
        """回報結果給 Lobby"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(('localhost', self.lobby_port))
            handler = ProtocolHandler(sock)
            
            handler.send_message({
                "type": "game_ended",
                "data": {
                    "room_id": self.room_id,
                    "results": results
                }
            })
            
            handler.close()
        except Exception as e:
            print(f"[Game] Failed to report to lobby: {e}")
    
    # 遊戲主迴圈：定期更新玩家狀態、自動下降、發送快照與檢查結束條件，直到遊戲結束。
    def game_loop(self):
        """遊戲主迴圈"""
        while not self.game_ended:
            try:
                current_time = time.time()
                
                # 更新所有玩家的遊戲狀態
                with self.player_lock:
                    for player_info in self.players.values():
                        game = player_info['game']
                        if game.update():
                            try:
                                self.send_snapshot(game.user_id)
                            except Exception as e:
                                print(f"[Game][error] auto-drop snapshot failed: {e}")
                
                # 定期發送快照
                if current_time - self.last_snapshot_time >= self.snapshot_interval:
                    with self.player_lock:
                        for user_id in self.players:
                            try:
                                self.send_snapshot(user_id)
                            except Exception as e:
                                print(f"[Game][error] periodic snapshot failed for {user_id}: {e}")
                        if self.debug_enabled:
                            # 簡易診斷：列印存活玩家與其行數
                            diag = []
                            for uid, info in self.players.items():
                                g = info['game']
                                diag.append(f"{uid[:6]} lines={g.lines} over={g.game_over}")
                            print(f"[Game][tick={self.tick}] players={len(self.players)} | " + ' | '.join(diag))
                    self.last_snapshot_time = current_time
                
                # 更新 tick
                self.tick += 1
                
                # 檢查遊戲結束
                if self.check_game_end():
                    self.end_game()
                    break
                
                # 控制更新頻率
                time.sleep(0.05)  # 20 FPS
                
            except Exception as e:
                print(f"[Game] Error in game loop: {e}")
                break
        if self.debug_enabled:
            print(f"[Game] Loop terminated reason={self.end_reason} tick={self.tick}")
    
    # 處理單顆客戶端連線：接收 HELLO/INPUT/LEAVE_GAME 等訊息並做相應處理，完畢後清理狀態。
    def handle_client(self, client_socket: socket.socket, addr):
        """處理客戶端連線"""
        print(f"[Game] New connection from {addr}")
        handler = ProtocolHandler(client_socket)
        user_id = None
        client_mode = None
        
        try:
            while not self.game_ended:
                message = handler.receive_message()
                if not message:
                    break
                
                msg_type = message.get('type')
                
                if msg_type == 'HELLO':
                    response = self.handle_hello(handler, message)
                    handler.send_message(response)
                    if response.get('type') != 'ERROR':
                        user_id = message.get('userId')
                        client_mode = response.get('mode', 'player')
                        # 在成功回覆 WELCOME 後檢查是否啟動遊戲（避免在持鎖狀態下呼叫 start_game 造成死結）
                        if client_mode == 'spectator':
                            self.send_initial_state_to_spectator(handler)
                        else:
                            should_start = False
                            with self.player_lock:
                                if len(self.players) == 2 and not self.game_started:
                                    should_start = True
                            if should_start:
                                self.start_game()

                elif msg_type == 'LEAVE_GAME' and user_id:
                    if client_mode == 'spectator':
                        print(f"[Game] Spectator {user_id} left the game.")
                        with self.player_lock:
                            self.spectators.pop(user_id, None)
                        break
                    # 玩家主動離開遊戲，立即結束比賽
                    print(f"[Game] Player {user_id} requested leave; ending game.")
                    self.end_reason = 'player_exit'
                    self.end_game()
                    break

                elif msg_type == 'INPUT' and user_id and client_mode != 'spectator':
                    self.handle_input(user_id, message)
                
        except Exception as e:
            print(f"[Game] Error: {e}")
        finally:
            # 清理
            if user_id:
                with self.player_lock:
                    if client_mode == 'spectator':
                        self.spectators.pop(user_id, None)
                        print(f"[Game] Spectator {user_id} disconnected; spectators={len(self.spectators)}")
                    elif user_id in self.players:
                        del self.players[user_id]
                        print(f"[Game] Player {user_id} disconnected; remaining={len(self.players)}")
            
            handler.close()
            print(f"[Game] Connection closed: {addr}")
    
    # 啟動遊戲伺服器：監聽 TCP 連線並為每個客戶端建立處理執行緒，直到遊戲結束或手動關閉。
    def start(self):
        """啟動遊戲伺服器"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('0.0.0.0', self.port))
        server_socket.listen(8)
        
        print(f"[Game] Game Server started on port {self.port} for room {self.room_id}")
        
        try:
            # 等待玩家連線
            timeout_time = time.time() + 30  # 30秒超時等待玩家

            while not self.game_ended:
                server_socket.settimeout(1.0)
                try:
                    client_socket, addr = server_socket.accept()
                    thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    with self.player_lock:
                        player_count = len(self.players)
                        started = self.game_started
                    if not started and player_count < 2 and time.time() >= timeout_time:
                        print(f"[Game] Not enough players joined before timeout. Shutting down room {self.room_id}.")
                        self.end_reason = 'insufficient_players'
                        self.end_game()
                        break
                    continue
                except Exception as exc:
                    print(f"[Game] Accept error: {exc}")

                # 定期檢查遊戲是否結束
                if self.game_ended:
                    break

            # 等待遊戲結束後釋放資源
            while not self.game_ended:
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n[Game] Shutting down...")
        finally:
            server_socket.close()

if __name__ == "__main__":
    import sys
    
    print(f"[Game] game_server.py started")
    print(f"[Game] Arguments: {sys.argv}")
    
    if len(sys.argv) < 4:
        print("Usage: game_server.py <port> <room_id> <lobby_port>")
        sys.exit(1)
    
    port = int(sys.argv[1])
    room_id = sys.argv[2]
    lobby_port = int(sys.argv[3])
    
    print(f"[Game] Creating server: port={port}, room={room_id}, lobby={lobby_port}")
    
    server = GameServer(port, room_id, lobby_port)
    server.start()