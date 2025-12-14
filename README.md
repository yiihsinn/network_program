# HW3 遊戲商店系統

## 快速開始

### Windows
```powershell
./store.bat
```

### macOS / Linux
```bash
./store.sh
```

### 重置資料
```bash
# Windows
./reset_data.bat

# macOS / Linux
./reset_data.sh
```

## 主選單

```
========================================
       HW3 Game Store System
========================================
  Server: linux2.cs.nycu.edu.tw
========================================

 1. Player Client (玩家)
 2. Developer Client (開發者)
 3. Exit
```

### 玩家功能
- 註冊/登入帳號
- 瀏覽商店、下載遊戲
- 建立/加入房間、開始遊戲
- 安裝 Plugin 擴充功能

### 開發者功能
- 建立新遊戲模板
- 上架/更新/下架遊戲

## 遊戲列表

| 遊戲 | 類型 | 人數 | 說明 |
|------|------|------|------|
| RockPaperScissors | CLI | 2 | 剪刀石頭布 |
| MultiClick | GUI | 2-4 | 多人點擊大戰 |

## 常見問題

### 畫面沒顯示/卡住
PowerShell 有時會進入阻塞模式，按 **Enter** 繼續即可。

### 重複登入
同一帳號只能在一處登入，若顯示「此帳號已在其他地方登入」請先登出另一端。
