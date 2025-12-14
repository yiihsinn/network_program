#!/usr/bin/env python3
"""
Developer Client - 遊戲開發者端
功能：註冊/登入、上架/更新/下架遊戲 (CLI Interaction)
包含完整錯誤處理
"""

import socket
import os
import sys
import json
import getpass
import time

try:
    from ..utils.protocol import ProtocolHandler, MessageBuilder
    from ..utils.utils import FileUtils, ConfigValidator
except ImportError:
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from utils.protocol import ProtocolHandler, MessageBuilder
    from utils.utils import FileUtils, ConfigValidator

class DeveloperClient:
    def __init__(self, host='127.0.0.1', port=15553):
        self.server_addr = (host, port)
        self.sock = None
        self.handler = None
        self.dev_id = None
        self.dev_name = None
        self.running = True

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10)
            self.sock.connect(self.server_addr)
            self.handler = ProtocolHandler(self.sock)
            return True
        except socket.timeout:
            print("❌ 連線逾時，請確認伺服器是否啟動")
            return False
        except ConnectionRefusedError:
            print("❌ 無法連線到伺服器，請確認伺服器是否啟動")
            return False
        except Exception as e:
            print(f"❌ 連線失敗: {e}")
            return False

    def send_request(self, action, data=None, timeout=30):
        """Send request with timeout and retry option."""
        if not self.handler: 
            print("❌ 未連線到伺服器")
            return None
        try:
            self.sock.settimeout(timeout)
            if not self.handler.send_message({"action": action, "data": data or {}}):
                print("❌ 發送請求失敗")
                return None
            response = self.handler.receive_message()
            
            # Check for force_logout message (duplicate login)
            if response and response.get('type') == 'force_logout':
                print(f"\n⚠️ 你的帳號已從其他地方登入，連線被中斷")
                print(f"   原因: {response.get('reason', 'Unknown')}")
                self.dev_id = None
                self.running = False
                return None
            
            return response
        except socket.timeout:
            print("❌ 伺服器回應逾時")
            retry = input("是否重試? (y/n): ").strip().lower()
            if retry == 'y':
                return self.send_request(action, data, timeout)
            return None
        except Exception as e:
            print(f"❌ 網路錯誤: {e}")
            return None

    def main_loop(self):
        print("=== 遊戲商店 - 開發者控制台 ===")
        if not self.connect():
            retry = input("是否重試連線? (y/n): ").strip().lower()
            if retry == 'y':
                if not self.connect():
                    return
            else:
                return

        try:
            while self.running:
                if not self.dev_id:
                    self.auth_menu()
                else:
                    self.dashboard_menu()
        except KeyboardInterrupt:
            print("\n正在離開...")
        finally:
            if self.handler:
                self.send_request('logout')
            print("再見!")

    def auth_menu(self):
        print("\n--- 身份驗證 ---")
        print("1. 登入")
        print("2. 註冊")
        print("3. 離開")
        choice = input("選擇: ").strip()
        
        if choice == '1':
            self.do_login()
        elif choice == '2':
            self.do_register()
        elif choice == '3':
            self.running = False
            
    def dashboard_menu(self):
        print(f"\n--- 開發者面板 ({self.dev_name}) ---")
        print("1. 我的遊戲列表")
        print("2. 上架新遊戲")
        print("3. 更新遊戲")
        print("4. 下架遊戲")
        print("5. 登出")
        choice = input("選擇: ").strip()
        
        if choice == '1':
            self.list_games()
        elif choice == '2':
            self.upload_game()
        elif choice == '3':
            self.update_game()
        elif choice == '4':
            self.remove_game()
        elif choice == '5':
            self.send_request('logout')
            self.dev_id = None
            print("已登出")
            
    def do_login(self):
        email = input("Email: ").strip()
        if not email:
            print("❌ Email 不可為空")
            return
        password = getpass.getpass("密碼: ").strip()
        if not password:
            print("❌ 密碼不可為空")
            return
        
        res = self.send_request('login', {'email': email, 'password': password})
        if res and res.get('success'):
            self.dev_id = res['data']['id']
            self.dev_name = res['data']['name']
            print(f"✅ 歡迎回來, {self.dev_name}!")
        else:
            error = res.get('error') if res else '網路錯誤'
            print(f"❌ 登入失敗: {error}")

    def do_register(self):
        print("\n--- 註冊新帳號 ---")
        name = input("開發者名稱: ").strip()
        if not name:
            print("❌ 名稱不可為空")
            return
            
        email = input("Email: ").strip()
        if not email:
            print("❌ Email 不可為空")
            return
        if '@' not in email:
            print("❌ Email 格式不正確")
            return
            
        password = getpass.getpass("密碼: ").strip()
        if not password:
            print("❌ 密碼不可為空")
            return
        if len(password) < 4:
            print("❌ 密碼至少需要 4 個字元")
            return

        res = self.send_request('register', {'name': name, 'email': email, 'password': password})
        if res and res.get('success'):
            print("✅ 註冊成功！請登入。")
        else:
            error = res.get('error') if res else '網路錯誤'
            print(f"❌ 註冊失敗: {error}")

    def list_games(self, select_mode=False):
        """List games. If select_mode=True, returns selected game or None."""
        res = self.send_request('list_my_games')
        if not res or not res.get('success'):
            print(f"❌ 錯誤: {res.get('error') if res else '連線錯誤'}")
            return None
        
        games = res.get('data', [])
        if not games:
            print("📭 尚未上架任何遊戲")
            return None
        
        print(f"\n{'#':<3} {'遊戲名稱':<20} {'版本':<10} {'狀態'}")
        print("-" * 50)
        for i, g in enumerate(games, 1):
            status = '✅ 上架中' if g.get('status', 'active') == 'active' else '🗃️ 已下架'
            print(f"{i:<3} {g['name']:<20} {g['latest_version']:<10} {status}")
        
        if select_mode:
            try:
                choice = input("\n選擇遊戲 (0 取消): ").strip()
                if not choice:
                    return None
                idx = int(choice) - 1
                if idx == -1:
                    return None
                if 0 <= idx < len(games):
                    return games[idx]
                print("❌ 選擇無效")
            except ValueError:
                print("❌ 請輸入數字")
            except KeyboardInterrupt:
                pass
            return None
        return None

    def _get_input(self, prompt, default=None, required=True, validator=None):
        """Get input with validation."""
        while True:
            if default:
                value = input(f"{prompt} [{default}]: ").strip()
                if not value:
                    value = default
            else:
                value = input(f"{prompt}: ").strip()
            
            if required and not value:
                print("❌ 此欄位為必填")
                continue
            
            if validator and value:
                valid, err = validator(value)
                if not valid:
                    print(f"❌ {err}")
                    continue
            
            return value

    def _validate_version(self, v):
        """Validate version format X.Y.Z"""
        parts = v.split('.')
        if len(parts) != 3:
            return False, "版本格式必須是 X.Y.Z (例如: 1.0.0)"
        for p in parts:
            if not p.isdigit():
                return False, "版本號各部分必須是數字"
        return True, None

    def _validate_int_range(self, min_val, max_val):
        """Create a validator for integer range."""
        def validator(v):
            try:
                n = int(v)
                if n < min_val or n > max_val:
                    return False, f"數值必須在 {min_val} 到 {max_val} 之間"
                return True, None
            except ValueError:
                return False, "請輸入數字"
        return validator

    def _create_or_fix_config(self, path, existing_config=None):
        """Create config interactively or fix missing fields."""
        print("\n📝 設定遊戲資訊...")
        config = existing_config or {}
        
        # Required fields
        config['name'] = self._get_input("遊戲名稱", config.get('name'))
        config['description'] = self._get_input("遊戲描述", config.get('description', '一款有趣的遊戲'))
        
        # Game type
        print("\n遊戲類型:")
        print("  1. CLI (命令列)")
        print("  2. GUI (圖形介面)")
        type_choice = self._get_input("選擇", '1' if config.get('type') == 'CLI' else '2')
        config['type'] = 'GUI' if type_choice == '2' else 'CLI'
        
        # Players
        config['min_players'] = int(self._get_input(
            "最少玩家數", 
            str(config.get('min_players', 2)),
            validator=self._validate_int_range(1, 10)
        ))
        config['max_players'] = int(self._get_input(
            "最多玩家數", 
            str(config.get('max_players', config['min_players'])),
            validator=self._validate_int_range(config['min_players'], 10)
        ))
        
        # Version
        config['version'] = self._get_input(
            "版本號", 
            config.get('version', '1.0.0'),
            validator=self._validate_version
        )
        
        # Exe command
        if 'exe_cmd' not in config:
            config['exe_cmd'] = ['python', 'client.py']
        
        return config

    def upload_game(self):
        print("\n" + "="*50)
        print("  📦 上架新遊戲")
        print("="*50)
        
        # Step 1: Get game folder path
        while True:
            path = input("\n遊戲資料夾路徑 (輸入 0 取消): ").strip()
            if path == '0':
                print("已取消")
                return
            
            if not path:
                print("❌ 路徑不可為空")
                continue
            
            if not os.path.exists(path):
                print(f"❌ 路徑不存在: {path}")
                continue
                
            if not os.path.isdir(path):
                print("❌ 路徑必須是資料夾")
                continue
            
            break
        
        # Step 2: Read or create config
        config_path = os.path.join(path, "game_config.json")
        config = None
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"✅ 找到設定檔: {config.get('name', '?')} v{config.get('version', '?')}")
                
                # Validate config
                valid, err = ConfigValidator.validate_game_config(config)
                if not valid:
                    print(f"⚠️ 設定檔有問題: {err}")
                    fix = input("是否手動補齊設定? (y/n): ").strip().lower()
                    if fix == 'y':
                        config = self._create_or_fix_config(path, config)
                    else:
                        print("已取消")
                        return
            except json.JSONDecodeError as e:
                print(f"❌ 設定檔 JSON 格式錯誤: {e}")
                fix = input("是否手動輸入設定? (y/n): ").strip().lower()
                if fix == 'y':
                    config = self._create_or_fix_config(path)
                else:
                    print("已取消")
                    return
        else:
            print("⚠️ 找不到 game_config.json")
            create = input("是否手動建立設定? (y/n): ").strip().lower()
            if create == 'y':
                config = self._create_or_fix_config(path)
                # Save the config
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
                print(f"✅ 已儲存設定到 {config_path}")
            else:
                print("已取消")
                return
        
        # Step 3: Confirm
        print("\n" + "-"*50)
        print("  📋 確認上架資訊")
        print("-"*50)
        print(f"  名稱:     {config['name']}")
        print(f"  版本:     {config['version']}")
        print(f"  類型:     {config['type']}")
        print(f"  玩家數:   {config['min_players']}-{config['max_players']}")
        print(f"  描述:     {config.get('description', '-')}")
        print(f"  資料夾:   {path}")
        print("-"*50)
        
        confirm = input("\n確認上架? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        # Step 4: Upload
        try:
            print("\n📦 打包檔案中...")
            b64_content = FileUtils.zip_directory(path)
            
            print(f"📤 上傳中 ({len(b64_content)//1024} KB)...")
            res = self.send_request('upload_game', {
                'game_config': config,
                'file_content_base64': b64_content
            }, timeout=60)
            
            if res and res.get('success'):
                print(f"\n✅ 上架成功!")
                print(f"   遊戲 ID: {res['data']['game_id']}")
                print("   您可以在「我的遊戲列表」中查看")
            else:
                error = res.get('error') if res else '連線錯誤'
                print(f"\n❌ 上架失敗: {error}")
                retry = input("是否重試? (y/n): ").strip().lower()
                if retry == 'y':
                    self.upload_game()
                    
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            retry = input("是否重試? (y/n): ").strip().lower()
            if retry == 'y':
                self.upload_game()

    def update_game(self):
        print("\n" + "="*50)
        print("  🔄 更新遊戲")
        print("="*50)
        
        print("\n選擇要更新的遊戲:")
        game = self.list_games(select_mode=True)
        if not game:
            return
        
        game_id = game['id']
        current_version = game['latest_version']
        print(f"\n正在更新: {game['name']} (目前版本: v{current_version})")
        
        # Get update folder
        while True:
            path = input("\n新版本資料夾路徑 (輸入 0 取消): ").strip()
            if path == '0':
                print("已取消")
                return
            
            if not path:
                print("❌ 路徑不可為空")
                continue
            
            if not os.path.exists(path):
                print(f"❌ 路徑不存在: {path}")
                continue
            
            break
        
        # Read config
        config_path = os.path.join(path, "game_config.json")
        config = None
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                print("❌ 設定檔 JSON 格式錯誤")
                fix = input("是否手動輸入設定? (y/n): ").strip().lower()
                if fix != 'y':
                    return
                config = self._create_or_fix_config(path, {'name': game['name']})
        else:
            print("⚠️ 找不到 game_config.json，使用現有設定")
            config = {'name': game['name'], 'type': game.get('type', 'CLI')}
            config = self._create_or_fix_config(path, config)
        
        # Check version
        new_version = config.get('version', '?')
        print(f"\n新版本: v{new_version}")
        
        if new_version == current_version:
            print("⚠️ 版本號與目前相同，建議更新版本號")
            change = input("是否修改版本號? (y/n): ").strip().lower()
            if change == 'y':
                new_version = self._get_input("新版本號", validator=self._validate_version)
                config['version'] = new_version
        
        # Release note
        note = self._get_input("更新說明", "Bug fixes and improvements")
        
        # Confirm
        print("\n" + "-"*50)
        print(f"  確認更新: v{current_version} → v{new_version}")
        print(f"  更新說明: {note}")
        print("-"*50)
        
        confirm = input("\n確認更新? (y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            return
        
        # Upload
        try:
            print("\n📦 打包檔案中...")
            b64_content = FileUtils.zip_directory(path)
            
            print("📤 上傳更新中...")
            res = self.send_request('update_game', {
                'game_id': game_id,
                'game_config': config,
                'file_content_base64': b64_content,
                'release_note': note
            }, timeout=60)
            
            if res and res.get('success'):
                print(f"\n✅ 更新成功! 新版本: v{res['data']['new_version']}")
            else:
                error = res.get('error') if res else '連線錯誤'
                print(f"\n❌ 更新失敗: {error}")
                retry = input("是否重試? (y/n): ").strip().lower()
                if retry == 'y':
                    self.update_game()
                    
        except Exception as e:
            print(f"❌ 錯誤: {e}")

    def remove_game(self):
        print("\n" + "="*50)
        print("  🗑️ 下架遊戲")
        print("="*50)
        
        print("\n選擇要下架的遊戲:")
        game = self.list_games(select_mode=True)
        if not game:
            return
        
        print(f"\n⚠️ 您即將下架: {game['name']}")
        print("   下架後玩家將無法下載此遊戲")
        
        confirm = input(f"\n請輸入遊戲名稱 '{game['name']}' 以確認下架: ").strip()
        if confirm != game['name']:
            print("❌ 名稱不符，已取消")
            return
        
        res = self.send_request('remove_game', {'game_id': game['id']})
        if res and res.get('success'):
            print("✅ 遊戲已下架 (已封存)")
        else:
            error = res.get('error') if res else '連線錯誤'
            print(f"❌ 下架失敗: {error}")

if __name__ == "__main__":
    import sys
    host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
    DeveloperClient(host=host).main_loop()
