#!/usr/bin/env python3
"""
Length-Prefixed Framing Protocol Implementation
每個訊息格式: [4-byte length (uint32, network byte order)] [body: length bytes]
"""

import struct
import socket
import json
import threading
from typing import Optional, Dict, Any

class ProtocolHandler:
    """處理 Length-Prefixed Framing Protocol 的類別"""
    
    # 增加最大訊息大小以支援大型遊戲檔案傳輸 (50MB)
    MAX_MESSAGE_SIZE = 50 * 1024 * 1024
    
    def __init__(self, sock: socket.socket):
        # 初始化 ProtocolHandler：保存 socket 並建立送訊鎖以確保多執行緒寫入安全
        self.sock = sock
        # Attempt to set keepalive if possible
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except:
            pass
            
        # 序列化 send，避免多執行緒/多來源寫入交錯造成分幀錯亂
        self._send_lock = threading.Lock()
        
    def send_message(self, data: Dict[str, Any]) -> bool:
        # 發送訊息：將 dict 序列化為 JSON 並以 4-byte length prefix 發送，具執行緒安全處理
        """發送訊息"""
        try:
            # 將資料轉為 JSON 字串
            json_str = json.dumps(data, ensure_ascii=False)
            message = json_str.encode('utf-8')
            
            # 檢查長度限制
            if len(message) > self.MAX_MESSAGE_SIZE:
                print(f"Message too large: {len(message)} bytes")
                return False
            
            # 建立長度前綴（4 bytes, network byte order）
            length_prefix = struct.pack('!I', len(message))
            
            # 發送長度前綴 + 訊息本體（具備執行緒安全）
            full_message = length_prefix + message
            with self._send_lock:
                # 處理部分發送
                total_sent = 0
                while total_sent < len(full_message):
                    sent = self.sock.send(full_message[total_sent:])
                    if sent == 0:
                        return False
                    total_sent += sent
                
            return True
            
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def receive_message(self) -> Optional[Dict[str, Any]]:
        # 接收訊息：讀取 4-byte 長度前綴後接收精確長度資料並解 JSON，回傳 dict 或 None
        """接收訊息"""
        try:
            # 先接收 4 bytes 的長度前綴
            length_data = self._receive_exact(4)
            if not length_data:
                return None
            
            # 解析長度（network byte order）
            message_length = struct.unpack('!I', length_data)[0]
            
            # 檢查長度限制
            if message_length <= 0 or message_length > self.MAX_MESSAGE_SIZE:
                print(f"Invalid message length: {message_length}")
                return None
            
            # 接收訊息本體
            message_data = self._receive_exact(message_length)
            if not message_data:
                return None
            
            # 解析 JSON
            json_str = message_data.decode('utf-8')
            return json.loads(json_str)
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            return None
        except Exception as e:
            print(f"Receive error: {e}")
            return None
    
    def _receive_exact(self, n: int) -> Optional[bytes]:
        # 低階接收工具：確保讀取到剛好 n bytes（處理可能的部分接收），失敗回傳 None
        """接收正好 n bytes 的資料"""
        data = b''
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.error:
                return None
        return data
    
    def close(self):
        # 關閉底層 socket 連線（忽略關閉錯誤）
        """關閉連線"""
        try:
            self.sock.close()
        except:
            pass

class MessageBuilder:
    """訊息建構器"""
    
    @staticmethod
    def build_request(collection: str, action: str, data: Dict[str, Any]) -> Dict[str, Any]:
        # 建立資料庫請求：回傳符合伺服器通訊格式的 dict
        """建立資料庫請求"""
        return {
            "collection": collection,
            "action": action,
            "data": data
        }
    
    @staticmethod
    def build_response(success: bool, data: Any = None, error: str = None) -> Dict[str, Any]:
        # 建立回應物件：根據 success 與資料/錯誤訊息組裝回傳格式
        """建立回應"""
        response = {"success": success}
        if data is not None:
            response["data"] = data
        if error:
            response["error"] = error
        return response
