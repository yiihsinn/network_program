#!/usr/bin/env python3
"""
Room Chat Plugin - 房間聊天功能
讓玩家在等待房間中可以互相聊天
"""

import threading

class RoomChatHandler:
    """處理房間聊天的 Plugin"""
    
    def __init__(self, send_func, username):
        """
        Args:
            send_func: 發送訊息到 server 的函數
            username: 當前用戶名
        """
        self.send_func = send_func
        self.username = username
        self.enabled = True
        self.messages = []  # 本地訊息暫存
        
    def send_message(self, text):
        """發送聊天訊息"""
        if not text.strip():
            return False
        
        self.send_func('room_chat', {
            'message': text[:200]  # 限制長度
        })
        return True
    
    def receive_message(self, data):
        """接收聊天訊息"""
        sender = data.get('sender', 'Unknown')
        message = data.get('message', '')
        timestamp = data.get('timestamp', '')
        
        self.messages.append({
            'sender': sender,
            'message': message,
            'timestamp': timestamp
        })
        
        # 顯示訊息
        if sender != self.username:
            print(f"\n💬 [{sender}]: {message}")
        
        return True
    
    def get_recent_messages(self, count=10):
        """取得最近的訊息"""
        return self.messages[-count:]
    
    def clear_messages(self):
        """清空訊息"""
        self.messages = []


def create_handler(send_func, username):
    """創建 Room Chat Handler 實例"""
    return RoomChatHandler(send_func, username)
