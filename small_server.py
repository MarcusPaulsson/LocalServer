import socket
import threading
from urllib.parse import parse_qs
import os
from cryptography.fernet import Fernet

# --- Configuration ---
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 80
NO_IP_HOSTNAME = 'your_ddns.net'  # Replace with your No-IP hostname if used
SUCCESS_REDIRECT_PATH = '/site/index.html'  # Path after successful login
SITE_ROOT = 'site'  # Directory for static files

# --- Encryption Key ---
#  Moved key to key.py
from key import ENCRYPTION_KEY # Keep the key in a separate file

# --- User Credentials ---
# Moved user credentials to users.py
from key import USERS  # Keep user data in a separate file

# --- Fernet Initialization ---
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_data(data: str) -> bytes:
    """Encrypts the given string data."""
    return fernet.encrypt(data.encode())

def decrypt_data(token: bytes) -> str:
    """Decrypts the given encrypted token."""
    return fernet.decrypt(token).decode()

def serve_static_file(conn, path):
    """Serves static files from the SITE_ROOT directory."""
    filepath = os.path.join(SITE_ROOT, path.lstrip('/'))
    print(f"Attempting to serve: {filepath}")  # Debugging line
    if os.path.isfile(filepath):
        try:
            with open(filepath, 'rb') as f:
                content = f.read()
            content_type = 'text/html'  # Default
            if filepath.endswith(".css"):
                content_type = 'text/css'
            elif filepath.endswith(".js"):
                content_type = 'application/javascript'
            elif filepath.endswith(".png"):
                content_type = 'image/png'
            elif filepath.endswith(".jpg") or filepath.endswith(".jpeg"):
                content_type = 'image/jpeg'

            response = f"HTTP/1.1 200 OK\r\n"
            response += f"Content-Type: {content_type}\r\n"
            response += f"Content-Length: {len(content)}\r\n"
            response += "\r\n"
            conn.sendall(response.encode('utf-8') + content)
        except Exception as e:
            print(f"Error serving static file: {e}")
            response = "HTTP/1.1 500 Internal Server Error\r\n\r\nInternal Server Error"
            conn.sendall(response.encode('utf-8'))
    else:
        response = "HTTP/1.1 404 Not Found\r\n\r\nNot Found"
        conn.sendall(response.encode('utf-8'))

def handle_client(conn, addr):
    """Handles client connections and the login/survey process."""
    print(f"Connected by {addr}")
    logged_in = False

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            decoded_data = data.decode('utf-8')
            print(f"Received from {addr}:\n{decoded_data}")

            request_lines = decoded_data.splitlines()
            if not request_lines:
                continue

            request_line = request_lines[0].split()
            if len(request_line) >= 2:
                method = request_line[0]
                path = request_line[1]

                if path == '/':
                    if logged_in:
                        # Redirect to the index.html page if logged in
                        response = "HTTP/1.1 302 Found\r\n"
                        response += f"Location: {SUCCESS_REDIRECT_PATH}\r\n"
                        response += "\r\n"
                        encoded_response = response.encode('utf-8')
                        conn.sendall(encoded_response)
                        break
                    else:
                        # Serve the login form if not logged in
                        response = "HTTP/1.1 200 OK\r\n"
                        response += "Content-Type: text/html\r\n"
                        response += "\r\n"
                        response += """
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>Login</title>
                        </head>
                        <body>
                            <h1>Login</h1>
                            <form method="post" action="/login">
                                <label for="username">Username:</label><br>
                                <input type="text" id="username" name="username"><br><br>
                                <label for="password">Password:</label><br>
                                <input type="password" id="password" name="password"><br><br>
                                <button type="submit">Login</button>
                            </form>
                        </body>
                        </html>
                        """
                        encoded_response = response.encode('utf-8')
                        conn.sendall(encoded_response)
                        break

                elif path == '/login' and method == 'POST':
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
                        if 'username' in form_data and 'password' in form_data:
                            username = form_data['username'][0]
                            password = form_data['password'][0]

                            if username in USERS and USERS[username] == password:
                                logged_in = True
                                # Redirect to the index.html page after successful login.  Let's send a welcome message.
                                response = "HTTP/1.1 200 OK\r\n"
                                response += "Content-Type: text/html\r\n"
                                response += "\r\n"
                                response += f"""
                                <!DOCTYPE html>
                                <html>
                                <head>
                                    <title>Welcome</title>
                                </head>
                                <body>
                                    <h1>Welcome, {username}!</h1>
                                    <p>You are now logged in.</p>
                                    <p><a href="{SUCCESS_REDIRECT_PATH}">Go to main site</a></p>
                                </body>
                                </html>
                                """
                                encoded_response = response.encode('utf-8')
                                conn.sendall(encoded_response)
                                break
                            else:
                                # Login failed
                                response = "HTTP/1.1 200 OK\r\n"
                                response += "Content-Type: text/html\r\n"
                                response += "\r\n"
                                response += """
                                <!DOCTYPE html>
                                <html>
                                <head>
                                    <title>Login Failed</title>
                                </head>
                                <body>
                                    <h1>Login Failed</h1>
                                    <p>Invalid username or password.</p>
                                    <p><a href="/">Try again</a></p>
                                </body>
                                </html>
                                """
                                encoded_response = response.encode('utf-8')
                                conn.sendall(encoded_response)
                                break
                        else:
                            response = "HTTP/1.1 400 Bad Request\r\n"
                            response += "Content-Type: text/plain\r\n"
                            response += "\r\n"
                            response += "Error: Missing username or password.\r\n"
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

                elif path.startswith(f"/{SITE_ROOT}/"):
                    serve_static_file(conn, path)
                    break

                elif path == '/submit' and method == 'POST' and logged_in:
                    # Process survey data (only if logged in)
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
                            break
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
                elif path == '/submit' and method == 'POST' and not logged_in:
                    # Redirect to login if not logged in
                    response = "HTTP/1.1 302 Found\r\n"
                    response += "Location: /\r\n"
                    response += "\r\n"
                    encoded_response = response.encode('utf-8')
                    conn.sendall(encoded_response)
                    break
                else:
                    # Handle other requests
                    response = "HTTP/1.1 404 Not Found\r\n"
                    response += "Content-Type: text/plain\r\n"
                    response += "\r\n"
                    response += "Not Found\r\n"
                    encoded_response = response.encode('utf-8')
                    conn.sendall(encoded_response)
                    break

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
    start_server()
