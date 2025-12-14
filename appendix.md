# Appendix: Implementation Details & Error Handling

## 1. Auth & Account Error Handling
### 1.1 Registration
-   **Username Taken**: If `username` (or `email`) exists in the target collection, return `error: "Username already taken"` (Code: `ERR_USER_EXISTS`).
-   **Invalid Format**: If password is empty or extremely short, return `error: "Password too weak"`.
-   **Type Mismatch**: Ensure Developer accounts cannot log in as Players and vice versa (separate collections).

### 1.2 Login
-   **Authentication Failure**: If user not found or password hash mismatch, return generic `error: "Invalid account or password"` to prevent enumeration attacks.
-   **Duplicate Login (Session Conflict)**:
    -   **Policy**: Kick Previous.
    -   **Implementation**: New login request arrives -> Server checks `online_users`. If user `ID` found:
        1.  Retrieve old socket.
        2.  Send `{"type": "force_logout", "reason": "Logged in from another location"}`.
        3.  Server closes old socket.
        4.  Old client receives message (or detects close), shows alert "You have been logged out", and returns to Login screen.
        5.  Server proceeds to admit new connection.

## 2. Developer Use Case Errors
### 2.1 D1: Upload Game
-   **Missing Metadata**: If `game_config.json` is missing fields (`exe_cmd`, `version`), Client validates first. If bypassed, Server rejects with `ERR_INVALID_CONFIG`.
-   **File Storage Failure**: If Server fails to write the zip file (disk full, permission), return `ERR_INTERNAL`. Transactionally rollback DB entry (delete the Game record if created).
-   **Bad Zip**: Server attempts to `zipfile.is_zipfile` before accepting. If invalid, reject.

### 2.2 D2: Update Game
-   **Permission Denied**: If `developer_id` of the game != current session's user ID, reject with `ERR_PERMISSION_DENIED`.
-   **Invalid Versioning**:
    -   New version <= Old version (lexicographical check or semver). Reject `ERR_VERSION_TOO_OLD`.
    -   "Same version" updates are generally disallowed to ensure client integrity (or allowed with overwrite warning). We will **disallow** same version re-upload.

### 2.3 D3: Remove Game
-   **Active Rooms**:
    -   **Policy**: "Mark for Removal" (Soft Delete).
    -   Set `status = "archived"` in DB.
    -   **Prevent New Rooms**: `handle_create_room` checks status. If `archived`, reject.
    -   **Existing Rooms**: Allow to finish.
    -   **Store Visibility**: Remove from `handle_list_games` results.

## 3. Player Use Case Errors
### 3.1 P1: Store & Details
-   **Empty Store**: Return empty list `[]`. Client shows "No games available yet".
-   **Missing Info**: If a game lacks `description`, display "No description available". If `avg_rating` is null, display "-".

### 3.2 P2: Download & Update
-   **Game Removed**: If client requests download for a game ID that is `archived` or deleted, Server returns `ERR_GAME_UNAVAILABLE`. Client alerts user.
-   **Integrity Check**:
    -   Post-download: Client unzips. If `zipfile.BadZipFile`, delete potentially corrupted folder and alert "Download Corrupted - Please Retry".

### 3.3 P3: Create/Join Room
-   **Version Mismatch**:
    -   **Joiner**: If Room is on v1.2, but Joiner has v1.0 (or no game) -> Client detects mismatch -> Auto-prompts "Update Required" -> Redirect to Download Flow.
    -   **Game Removed**: If User tries to start a room for a valid local game, but Server says it's `archived`, allow playing (Local Mode) or Reject (Online Mode)? **Decision**: Reject creation of PUBLIC rooms for archived games.
-   **Room Full**: Standard HW2 logic.

### 3.4 P4: Review
-   **No Play Record**: Server checks `GameLog` or `User.play_history`. If not found, reject `ERR_NOT_PLAYED`.
-   **Rate Bounds**: If score < 1 or > 5, reject.
-   **Duplicate Review**: If user already reviewed, **Overwrite** previous review (update timestamp).

## 4. Plugin System Errors (Bonus)
-   **Download Fail**: If plugin download fails, catch exception, delete partial file. Plugin status remains `Not Installed`.
-   **Runtime Crash**: Wrap Plugin execution in `try-catch`. If a plugin crashes the UI rendering, disable the plugin and log error to console, keeping the main Lobby alive.
-   **Compatibility**: If Player A (Plugin installed) and Player B (No Plugin) are in room:
    -   Player A sends "Chat Message".
    -   Server broadcasts.
    -   Player B receives unknown message type (or plugin-specific type).
    -   **Fallback**: Player B's client **must ignore** unknown message types instead of crashing.

## 5. Security & Network Protocols
-   **Path Traversal**: Sanitize all version/gameID strings before using in file paths.
-   **Exec Safety**: No `shell=True` in `subprocess`.
-   **Base64**: large payloads. Increase `MAX_MESSAGE_SIZE` in `protocol.py` (e.g. to 10MB or stream in chunks). **Decision**: For this HW, increase limit to ~50MB to handle simple games easily.

## 6. Config Schema
**game_config.json**
```json
{
    "game_id": "auto_assigned_by_server_on_first_upload",
    "name": "Snake",
    "version": "1.0.0",
    "exe_cmd": ["python", "main.py"],
    "min_players": 1,
    "max_players": 2,
    "type": "GUI"
}
```
**Decision on `game_id`**: Developer sets `name`. Server assigns ID `snake_123456`. Developer Client updates local config or tracks mapping.
Better approach for HW: Developer chooses a unique `game_id` manually? Or Server generates.
**Refined Strategy**: Developer provides `name` and local folder. Server generates `game_id`. Client saves this `game_id` to a local `.dev_meta` file to track identity for future updates.
