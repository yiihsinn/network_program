#!/usr/bin/env python3
"""
Game Template Generator
Interactive helper script for developers to create a new game project structure.
"""

import os
import json
import sys

CLIENT_TEMPLATE = '''#!/usr/bin/env python3
import sys
import socket

def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <server_ip> <server_port>")
        return

    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    
    print(f"Connecting to Game Server at {server_ip}:{server_port}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server_ip, server_port))
        print("Connected! Waiting for message...")
        while True:
            data = s.recv(1024)
            if not data: break
            print("Server says:", data.decode())
            # TODO: Implement game logic interacting with server here
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
'''

SERVER_TEMPLATE = '''#!/usr/bin/env python3
import sys
import socket
import threading

def handle_client(conn, addr):
    print(f"Player {addr} connected")
    conn.send(b"Welcome to the game!\\n")
    # TODO: Implement game logic here

def main():
    if len(sys.argv) < 3:
        print("Usage: python server.py <port> <num_players>")
        return

    port = int(sys.argv[1])
    num_players = int(sys.argv[2])

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', port))
    s.listen(num_players)
    
    print(f"Game Server listening on {port} for {num_players} players...")
    
    clients = []
    while len(clients) < num_players:
        conn, addr = s.accept()
        clients.append(conn)
        threading.Thread(target=handle_client, args=(conn, addr)).start()
    
    # TODO: Game Loop...

if __name__ == "__main__":
    main()
'''

def get_input(prompt, default=None, validator=None):
    """Get input with optional default and validation."""
    while True:
        if default:
            value = input(f"{prompt} [{default}]: ").strip()
            if not value:
                value = default
        else:
            value = input(f"{prompt}: ").strip()
        
        if validator:
            valid, err = validator(value)
            if not valid:
                print(f"  ❌ {err}")
                continue
        return value

def validate_version(v):
    parts = v.split('.')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return False, "Version must be X.Y.Z format (e.g., 1.0.0)"
    return True, None

def validate_int(min_val=1, max_val=100):
    def validator(v):
        try:
            n = int(v)
            if n < min_val or n > max_val:
                return False, f"Must be between {min_val} and {max_val}"
            return True, None
        except:
            return False, "Must be a number"
    return validator

def create_template(output_dir=None):
    print("\n" + "="*50)
    print("  🎮 Game Template Generator")
    print("="*50 + "\n")
    
    # Get game information interactively
    name = get_input("Game name", "MyGame")
    description = get_input("Description", "A fun multiplayer game")
    
    print("\nGame type:")
    print("  1. CLI (Command Line)")
    print("  2. GUI (Graphical)")
    type_choice = get_input("Select", "1")
    game_type = "GUI" if type_choice == "2" else "CLI"
    
    min_players = int(get_input("Minimum players", "2", validate_int(1, 10)))
    max_players = int(get_input("Maximum players", str(min_players), validate_int(min_players, 10)))
    
    version = get_input("Initial version", "1.0.0", validate_version)
    
    # Determine output directory
    if not output_dir:
        output_dir = get_input("Output folder", f"games/{name}")
    
    # Create config
    config = {
        "name": name,
        "version": version,
        "description": description,
        "type": game_type,
        "exe_cmd": ["python", "client.py"],
        "min_players": min_players,
        "max_players": max_players
    }
    
    # Summary
    print("\n" + "-"*50)
    print("  📋 Summary")
    print("-"*50)
    print(f"  Name:        {name}")
    print(f"  Description: {description}")
    print(f"  Type:        {game_type}")
    print(f"  Players:     {min_players}-{max_players}")
    print(f"  Version:     {version}")
    print(f"  Output:      {output_dir}/")
    print("-"*50)
    
    confirm = input("\nCreate project? (Y/n): ").strip().lower()
    if confirm == 'n':
        print("Cancelled.")
        return
    
    # Create files
    if os.path.exists(output_dir):
        print(f"⚠️  Directory '{output_dir}' already exists. Overwriting config...")
    else:
        os.makedirs(output_dir)
    
    # Write game_config.json
    with open(os.path.join(output_dir, 'game_config.json'), 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    # Write client.py if it doesn't exist
    client_path = os.path.join(output_dir, 'client.py')
    if not os.path.exists(client_path):
        with open(client_path, 'w') as f:
            f.write(CLIENT_TEMPLATE.strip())
    
    # Write server.py if it doesn't exist
    server_path = os.path.join(output_dir, 'server.py')
    if not os.path.exists(server_path):
        with open(server_path, 'w') as f:
            f.write(SERVER_TEMPLATE.strip())
    
    print(f"\n✅ Game project '{name}' created successfully!")
    print(f"\n📁 Files created in: {output_dir}/")
    print("   - game_config.json")
    print("   - client.py")
    print("   - server.py")
    print("\n📝 Next steps:")
    print(f"   1. Edit client.py and server.py to implement your game")
    print(f"   2. Use Developer Client to upload: ./start_developer.bat")
    print(f"   3. Select 'Upload New Game' and enter path: {output_dir}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        create_template(sys.argv[1])
    else:
        create_template()
