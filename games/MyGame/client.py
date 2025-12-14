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
            # Implement game logic interacting with server here
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()