# HW3 Game Store System Implementation Plan

## Goal
Implement a fully functional Game Store System where Developers can upload/update games and Players can browse/download/play games. The system must be robust, modular, and handle errors gracefully.

## Architecture

### 1. Server Side
*   **Database Server (`db_server.py`)**: Reuse HW2 `DatabaseServer`.
    *   Collections: `User`, `Developer`, `Room`, `Game`, `GameLog`, `Plugin` (Bonus).
*   **Developer Server (`developer_server.py`)**: NEW.
    *   Handles developer login, game uploads, updates, removal.
    *   Auth: Independent Developer Account system.
    *   File Storage: `server/uploaded_games/<game_id>/<version>/`
*   **Lobby Server (`lobby_server.py`)**: EXTEND HW2.
    *   Auth: Player Account system (Session Management).
    *   Lobby Core: Room management, Online users.
    *   Store: List games, Get Details, Download.
    *   Plugin Manager: Serve plugin metadata.
*   **Shared Protocol**: Reuse `protocol.py`. File transfer via **Base64** inside JSON.

### 2. Client Side
*   **Developer Client (`developer_client.py`)**: NEW.
    *   Auth: Login/Register.
    *   Menu: Manage My Games (Upload/Update/Remove).
*   **Player Client (`lobby_client.py`)**: NEW (Rewrite/Refactor HW2).
    *   Auth: Login/Register.
    *   Lobby View: Real-time update of Rooms/Players.
    *   Store View: Browse, Detail, Review.
    *   Library: Manage local downloads.
    *   Launcher: Spawn game processes.
    *   Plugin Manager (Bonus): Install/Remove plugins.

### 3. Data Structures & Schema

#### Auth & Session Model
*   **Register**: `username` (or email) must be unique within `User` or `Developer` collection. Password stored as SHA256 hash.
*   **Session Policy**: "Single-Session per Account".
    *   **Strategy**: **Kick Previous**. When a new login occurs for an existing `user_id`, the server finds the old connection in `online_users`, sends a `force_logout` message, and closes that socket.
*   **Security**: Minimal implementation (socket association). No complex tokens for this HW unless needed.

#### Database Collections
*   `User`: `{id, name, passwordHash, ...}`
*   `Developer`: `{id, name, passwordHash, ...}`
*   `Game`:
    *   `id`, `developer_id`
    *   `name`, `description`, `type`
    *   `latest_version`: "1.0.0"
    *   `versions`: `[{version, release_note, timestamp}]`
    *   `rating_sum`: int, `rating_count`: int (cached for speed)
    *   `reviews`: `[{user_id, score, comment, timestamp}]`
*   `Room`:
    *   `id`, `host_id`, `status`
    *   `game_id`: The ID of the game selected for this room.
    *   `game_version`: The version of the game this room is using (usually `latest_version` at creation time, or specific).
*   `Plugin` (Bonus):
    *   `id`, `name`, `description`, `version`, `file_path`

### 4. Detailed Component Logic

#### Lobby View & Room Binding
*   **Lobby View**:
    *   **User List**: `[Name, Status (Idle/Room/Game), GameID if playing]`
    *   **Room List**: `[ID, Name, Host, Game Name, Players/Max, Status]`
*   **Room Version Binding**:
    *   **Create Room**: User picks Game -> Server checks if User has `latest_version` (or requires Client to send version info). Server locks Room to that `game_id` + `version`.
    *   **Join Room**: User requests Join -> Server sends `(game_id, version)`. Client checks local library. If missing/mismatch -> Prompt "Download Required" -> Auto-redirect to Download or Fail.

#### Game Template (Phased)
1.  **Phase 1 (Basic)**: `start_game` script calling a CLI Python script.
2.  **Phase 2 (GUI)**: E.g., `PyQt` or `Tkinter` wrapper.
3.  **Phase 3 (Multi-player)**: Game Logic using `socket` to connect to Game Server (reusing HW2 game server architecture but dynamic).

#### Plugin Architecture (Bonus)
*   **Registry**: Server stores available plugins in `Plugin` collection.
*   **Client Manager**: `plugins/` local folder.
    *   `install(plugin_id)`: Download -> Unzip to `plugins/<name>/`.
*   **Runtime**:
    *   Lobby Client loads available plugins on startup.
    *   **In-Room**: If `ChatPlugin` is present, render extra UI box. If not, simple view.

## 5. Verification Plan

### Automated Tests
*   `verify_auth.py`: Register user A, Login A (Client 1), Login A (Client 2), Verify Client 1 disconnected.
*   `verify_flow.py`: Dev Upload -> Player Download -> Integrity Check.

### Manual Verification
*   **Persistence**: Stop DB Server -> Start DB Server -> Check Data.
*   **Multi-Player**: Run `client_Start.sh` twice (Player1, Player2).
    *   Player 1 creates room (Game A v1.0).
    *   Dev updates Game A to v2.0.
    *   Player 2 tries to join -> Should flag version mismatch or handle gracefully (depending on policy).
