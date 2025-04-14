from flask import Flask, request, redirect, url_for, render_template, jsonify
import os
import datetime
import time
import importlib
import psutil
import sqlite3

# --- Configuration ---
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 80
NO_IP_HOSTNAME = 'your_ddns.net'  # Replace with your No-IP hostname if used
DATABASE_NAME = 'server_data.db'

# --- Encryption & User Config ---
from key import ENCRYPTION_KEY, USERS
from cryptography.fernet import Fernet
fernet = Fernet(ENCRYPTION_KEY)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Replace with a persistent key for production
logged_in = False  # For demo purposes only
app.start_time = time.time()  # Start time for uptime

# --- Helper Functions for Dynamic Constants ---
def load_constants():
    """
    Load dynamic constants from the dynamic_constants.py module.
    Returns the current temperature.
    """
    try:
        import dynamic_constants as dc
        importlib.reload(dc)  # Ensure we get the latest version
        return dc.current_temperature
    except ImportError:
        return 20  # Default value

def write_constants(current_temperature):
    """
    Overwrites dynamic_constants.py with the updated temperature.
    """
    content = (
        f"current_temperature = {current_temperature}\n"
    )
    with open("dynamic_constants.py", "w") as f:
        f.write(content)

def get_latest_server_data():
    """Retrieves the latest server information from the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cpu_percent, memory_percent, disk_percent
        FROM server_data
        ORDER BY timestamp DESC
        LIMIT 1
    ''')
    latest_data = cursor.fetchone()
    conn.close()
    if latest_data:
        return {
            'cpu': latest_data[0],
            'memory_percent': latest_data[1],
            'disk_percent': latest_data[2]
        }
    return None

def get_recent_server_data(limit=100):
    """Retrieves recent server information from the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(f'''
        SELECT timestamp, cpu_percent, memory_percent, disk_percent
        FROM server_data
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    recent_data = cursor.fetchall()
    conn.close()
    if recent_data:
        timestamps = [row[0] for row in reversed(recent_data)]
        cpu_percent = [row[1] for row in reversed(recent_data)]
        memory_percent = [row[2] for row in reversed(recent_data)]
        disk_percent = [row[3] for row in reversed(recent_data)]
        latest = {'cpu': recent_data[0][1], 'memory_percent': recent_data[0][2], 'disk_percent': recent_data[0][3]}
        return {'timestamps': timestamps, 'cpu_percent': cpu_percent,
                'memory_percent': memory_percent, 'disk_percent': disk_percent, 'latest': latest}
    return None

# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('login_form'))

@app.route('/login')
def login_form():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    if username in USERS and USERS[username] == password:
        global logged_in
        logged_in = True
        return redirect(url_for('dashboard'))
    else:
        return render_template('login_failed.html')

@app.route('/dashboard')
def dashboard():
    if logged_in:
        current_temperature = load_constants()
        latest_server_info = get_latest_server_data()
        return render_template('dashboard.html',
                                current_temperature=current_temperature,
                                server_info=latest_server_info)
    else:
        return redirect(url_for('login_form'))

@app.route('/submit', methods=['POST'])
def submit():
    if not logged_in:
        return redirect(url_for('index'))
    answer = request.form.get('answer')
    if answer:
        encrypted_answer = fernet.encrypt(answer.encode())
        print("\n--- Received Encrypted Answer ---")
        print("Encrypted:", encrypted_answer.decode())
        try:
            decrypted_answer = fernet.decrypt(encrypted_answer).decode()
            print("Decrypted:", decrypted_answer)
        except Exception as e:
            print("Decryption Error:", e)
        return render_template('submission_successful.html')
    else:
        return "Error: Missing or empty 'answer' field.", 400

@app.route('/update_temperature', methods=['POST'])
def update_temperature():
    current_temperature = load_constants()
    data = request.json
    if "current_temperature" in data:
        current_temperature = data["current_temperature"]
    write_constants(current_temperature)
    return jsonify(success=True, current_temperature=current_temperature)

@app.route('/server_info')
def server_info():
    latest_data = get_latest_server_data()
    if latest_data:
        return jsonify(latest_data)
    else:
        return jsonify({'cpu': 'N/A', 'memory_percent': 'N/A', 'disk_percent': 'N/A'}), 500

@app.route('/recent_server_data')
def recent_server_data():
    data = get_recent_server_data()
    if data:
        return jsonify(data)
    else:
        return jsonify({'error': 'Could not retrieve recent server data'}), 500

@app.route('/time')
def get_time():
    now = datetime.datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({'time': current_time})

@app.route('/uptime')
def get_uptime():
    uptime = time.time() - app.start_time
    return jsonify({'uptime': int(uptime)})

@app.route('/floor_plan')
def floor_plan():
    if logged_in:
        return render_template('floor_plan.html')
    else:
        return redirect(url_for('login_form'))

# @app.route('/cpu_temperature')
# def cpu_temperature():
#     try:
#         temps = psutil.sensors_temperatures()
#         cpu_temps = []
#         for name, entries in temps.items():
#             for entry in entries:
#                 if 'core' in name.lower() or 'cpu' in name.lower():
#                     cpu_temps.append(entry.current)
#         if cpu_temps:
#             return jsonify({'temperature': round(sum(cpu_temps) / len(cpu_temps), 1)})
#         else:
#             return jsonify({'temperature': 'N/A'})
#     except Exception as e:
#         print(f"Error getting CPU temperature: {e}")
#         return jsonify({'temperature': 'Error'})

if __name__ == '__main__':
    print(f"Server listening on {SERVER_HOST}:{SERVER_PORT} (Flask)")
    print(f"Accessible via No-IP hostname: {NO_IP_HOSTNAME}:{SERVER_PORT} (if port forwarding and DNS are set up correctly)")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=True)