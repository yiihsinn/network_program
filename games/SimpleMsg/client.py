import sys
import socket
import signal

def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <server_ip> <server_port>")
        return

    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    
    print(f"Connecting to Game Server at {server_ip}:{server_port}...")
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(30)  # 30 second timeout
        s.connect((server_ip, server_port))
        print("Connected! Waiting for message...")
        print("(Press Ctrl+C to exit game)")
        
        s.settimeout(5)  # 5 second read timeout
        while True:
            try:
                data = s.recv(1024)
                if not data: 
                    print("Server closed connection.")
                    break
                print("Server says:", data.decode())
            except socket.timeout:
                continue  # No message, keep waiting
            except KeyboardInterrupt:
                print("\nExiting game...")
                break
                
    except ConnectionRefusedError:
        print(f"Cannot connect to {server_ip}:{server_port}")
    except KeyboardInterrupt:
        print("\nExiting game...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if s:
            try:
                s.close()
            except:
                pass
        print("Game client exited.")

if __name__ == "__main__":
    main()