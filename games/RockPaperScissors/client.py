#!/usr/bin/env python3
"""
RockPaperScissors Client - Level A (CLI 2-Player)
"""
import sys
import socket
import json
import threading

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

def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <server_ip> <server_port> [player_name]")
        return

    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    player_name = sys.argv[3] if len(sys.argv) > 3 else "Player"
    
    print("=" * 40)
    print("   剪刀石頭布 - Rock Paper Scissors")
    print("=" * 40)
    print(f"連線到 {server_ip}:{server_port}...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(60)
    
    try:
        sock.connect((server_ip, server_port))
        # Send player name on connect
        send_json(sock, {"type": "join", "name": player_name})
        print(f"已連線！玩家: {player_name}，等待遊戲開始...")
        
        running = True
        while running:
            msg = recv_json(sock)
            if not msg:
                print("連線中斷")
                break
            
            msg_type = msg.get('type')
            
            if msg_type == 'welcome':
                print(f"你是 Player {msg.get('player_id')}")
                print(msg.get('message', ''))
            
            elif msg_type == 'game_start':
                print("\n" + "=" * 40)
                print(msg.get('message', '遊戲開始！'))
                print(f"你是: {msg.get('you_are')}")
                print("=" * 40)
            
            elif msg_type == 'round_start':
                scores = msg.get('scores', [0, 0])
                print(f"\n--- 第 {msg.get('round')} 回合 ---")
                print(f"目前比數: {scores[0]} - {scores[1]}")
                print("\n請選擇:")
                print("  R = 石頭 (Rock)")
                print("  P = 布 (Paper)")
                print("  S = 剪刀 (Scissors)")
                
                # Small delay to let any buffered data settle
                import time
                time.sleep(0.1)
                
                choice = ''
                while choice not in ('R', 'P', 'S'):
                    try:
                        user_in = input("你的選擇 (R/P/S): ").strip().upper()
                        if user_in in ('R', 'P', 'S'):
                            choice = user_in
                        elif user_in:
                            print(f"'{user_in}' 無效，請輸入 R, P 或 S")
                        # Empty input - continue loop silently
                    except (EOFError, KeyboardInterrupt):
                        choice = 'R'
                        break
                
                choice_name = {'R': '石頭', 'P': '布', 'S': '剪刀'}[choice]
                send_json(sock, {"type": "choice", "value": choice})
                print(f"你選了 {choice_name}，等待對手...")
            
            elif msg_type == 'round_result':
                print(f"\n你出: {msg.get('your_choice')}")
                print(f"對手: {msg.get('opponent_choice')}")
                print(f"結果: {msg.get('result')}")
                scores = msg.get('scores', [0, 0])
                print(f"比數: {scores[0]} - {scores[1]}")
            
            elif msg_type == 'game_over':
                print("\n" + "=" * 40)
                print("遊戲結束！")
                print(f"最終比數: {msg.get('final_scores')}")
                print(f"{msg.get('your_result')}")
                print("=" * 40)
                running = False
        
    except socket.timeout:
        print("連線逾時")
    except ConnectionRefusedError:
        print(f"無法連線到 {server_ip}:{server_port}")
    except KeyboardInterrupt:
        print("\n遊戲中斷")
    except Exception as e:
        print(f"錯誤: {e}")
    finally:
        sock.close()
        print("\n遊戲結束，按 Enter 繼續...")
        try:
            input()
        except:
            pass

if __name__ == "__main__":
    main()
