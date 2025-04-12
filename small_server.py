import socket
import threading
from urllib.parse import parse_qs
from cryptography.fernet import Fernet

from key import ENCRYPTION_KEY as ENCRYPTION_KEY
# --- Configuration ---
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 80
NO_IP_HOSTNAME = 'marcuspaulsson.ddns.net'

# --- Encryption Key (Keep this SECRET and SECURE in a real application!) ---
# Generate a new key: key = Fernet.generate_key().decode()
fernet = Fernet(ENCRYPTION_KEY.encode())

def encrypt_data(data: str) -> bytes:
    """Encrypts the given string data."""
    return fernet.encrypt(data.encode())

def decrypt_data(token: bytes) -> str:
    """Decrypts the given encrypted token."""
    return fernet.decrypt(token).decode()

def handle_client(conn, addr):
    """Handles client connections and HTTP requests for the survey."""
    print(f"Connected by {addr}")
    try:
        while True:
            data = conn.recv(4096)  # Increase buffer size for potential POST data
            if not data:
                break
            decoded_data = data.decode('utf-8')
            print(f"Received from {addr}:\n{decoded_data}")

            # --- Basic HTTP Request Parsing ---
            request_lines = decoded_data.splitlines()
            if not request_lines:
                continue

            request_line = request_lines[0].split()
            if len(request_line) >= 2:
                method = request_line[0]
                path = request_line[1]

                if path == '/':
                    # Serve the survey form
                    response = "HTTP/1.1 200 OK\r\n"
                    response += "Content-Type: text/html\r\n"
                    response += "\r\n"
                    response += """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Simple Survey</title>
                    </head>
                    <body>
                        <h1>Please answer the question:</h1>
                        <form method="post" action="/submit">
                            <label for="answer">Your Answer:</label><br>
                            <input type="text" id="answer" name="answer"><br><br>
                            <button type="submit">Submit</button>
                        </form>
                    </body>
                    </html>
                    """
                    encoded_response = response.encode('utf-8')
                    conn.sendall(encoded_response)
                    break  # Send response and close connection for this request

                elif path == '/submit' and method == 'POST':
                    # Process the submitted data
                    content_length = 0
                    for line in request_lines:
                        if line.startswith('Content-Length:'):
                            try:
                                content_length = int(line.split(': ')[1])
                            except ValueError:
                                content_length = 0
                            break

                    if content_length > 0:
                        body = decoded_data[decoded_data.find('\r\n\r\n') + 4:]
                        form_data = parse_qs(body)
                        if 'answer' in form_data and form_data['answer']:
                            answer = form_data['answer'][0]
                            encrypted_answer = encrypt_data(answer)
                            print(f"\n--- Received Encrypted Answer from {addr} ---")
                            print(f"Encrypted: {encrypted_answer.decode()}")

                            # In a real scenario, you would store the encrypted data
                            # For demonstration, we decrypt and print it back
                            try:
                                decrypted_answer = decrypt_data(encrypted_answer)
                                print(f"Decrypted: {decrypted_answer}")
                            except Exception as e:
                                print(f"Decryption Error: {e}")

                            response = "HTTP/1.1 200 OK\r\n"
                            response += "Content-Type: text/html\r\n"
                            response += "\r\n"
                            response += """
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <title>Submission Successful</title>
                            </head>
                            <body>
                                <h1>Thank you for your submission!</h1>
                            </body>
                            </html>
                            """
                            encoded_response = response.encode('utf-8')
                            conn.sendall(encoded_response)
                            break  # Send response and close connection

                        else:
                            response = "HTTP/1.1 400 Bad Request\r\n"
                            response += "Content-Type: text/plain\r\n"
                            response += "\r\n"
                            response += "Error: Missing or empty 'answer' field.\r\n"
                            encoded_response = response.encode('utf-8')
                            conn.sendall(encoded_response)
                            break

                    else:
                        response = "HTTP/1.1 400 Bad Request\r\n"
                        response += "Content-Type: text/plain\r\n"
                        response += "\r\n"
                        response += "Error: No data received in POST request.\r\n"
                        encoded_response = response.encode('utf-8')
                        conn.sendall(encoded_response)
                        break

                else:
                    # Handle other requests (e.g., favicon)
                    response = "HTTP/1.1 404 Not Found\r\n"
                    response += "Content-Type: text/plain\r\n"
                    response += "\r\n"
                    response += "Not Found\r\n"
                    encoded_response = response.encode('utf-8')
                    conn.sendall(encoded_response)
                    break  # Send response and close connection

    except ConnectionResetError:
        print(f"Connection with {addr} reset.")
    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        conn.close()
        print(f"Connection with {addr} closed.")

def start_server():
    """Starts the HTTP server."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((SERVER_HOST, SERVER_PORT))
            s.listen()
            print(f"Server listening on {SERVER_HOST}:{SERVER_PORT} (HTTP)")
            print(f"Accessible via No-IP hostname: {NO_IP_HOSTNAME}:{SERVER_PORT} (if port forwarding and DNS are set up correctly)")
            while True:
                conn, addr = s.accept()
                client_thread = threading.Thread(target=handle_client, args=(conn, addr))
                client_thread.start()
    except Exception as e:
        print(f"Error starting server: {e}")
    finally:
        print("Server stopped.")

if __name__ == "__main__":
    # --- Generate a Fernet key if you haven't already ---
    # from cryptography.fernet import Fernet
    # key = Fernet.generate_key().decode()
    # print(f"Generated Fernet Key: {key}")
    # --- Replace 'YOUR_GENERATED_FERNET_KEY_HERE' with the key you generated ---
    if ENCRYPTION_KEY == "YOUR_GENERATED_FERNET_KEY_HERE":
        print("WARNING: Please replace 'YOUR_GENERATED_FERNET_KEY_HERE' with a real generated Fernet key for security!")

    start_server()