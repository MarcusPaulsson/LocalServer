from flask import Flask, request, redirect, url_for, render_template, jsonify
import os
import datetime
import time
import importlib
import psutil  # New: library for fetching system information

# --- Configuration ---
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 80
NO_IP_HOSTNAME = 'your_ddns.net'  # Replace with your No-IP hostname if used

# --- Encryption & User Config (unchanged) ---
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
    Returns a tuple (device_status, current_temperature).
    """
    import dynamic_constants as dc
    importlib.reload(dc)  # Ensure we get the latest version
    return dc.device_status, dc.current_temperature

def write_constants(device_status, current_temperature):
    """
    Overwrites dynamic_constants.py with the updated settings.
    """
    content = (
        "device_status = " + repr(device_status) + "\n" +
        "current_temperature = " + str(current_temperature) + "\n"
    )
    with open("dynamic_constants.py", "w") as f:
        f.write(content)

# --- Routes for Login, Dashboard, etc. ---
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
        # Load dynamic constants for use in the dashboard template
        device_status, current_temperature = load_constants()
        return render_template('dashboard.html',
                               device_status=device_status,
                               current_temperature=current_temperature)
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

# --- New Endpoint: Update Settings ---
@app.route('/update_status', methods=['POST'])
def update_status():
    # Load current settings from dynamic_constants.py
    device_status, current_temperature = load_constants()
    data = request.json
    # Update device status if provided
    if "device" in data and "status" in data:
        device = data["device"]
        status = data["status"]
        device_status[device] = status
    # Update temperature if provided
    if "current_temperature" in data:
        current_temperature = data["current_temperature"]
    # Write back to the dynamic file
    write_constants(device_status, current_temperature)
    return jsonify(success=True,
                   device_status=device_status,
                   current_temperature=current_temperature)

# --- New Endpoint: Server Information ---
@app.route('/server_info')
def server_info():
    """
    Returns system metrics (CPU, memory, disk usage) for the local machine.
    """
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return jsonify(
        cpu=cpu_percent,
        memory_total=mem.total,
        memory_available=mem.available,
        memory_percent=mem.percent,
        disk_total=disk.total,
        disk_used=disk.used,
        disk_percent=disk.percent
    )

# --- Other Routes (Time, Uptime, Floor Plan) ---
@app.route('/time')
def get_time():
    now = datetime.datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({'time': current_time})

@app.route('/uptime')
def get_uptime():
    uptime = time.time() - app.start_time
    return jsonify({'uptime': int(uptime)})

@app.route('/set_device_status/<device>/<status>')
def set_device_status(device, status):
    if not logged_in:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    # Load and update settings dynamically
    device_status, current_temperature = load_constants()
    if device in device_status:
        if status.upper() in ["ON", "OFF"]:
            device_status[device] = status.upper()
            write_constants(device_status, current_temperature)
            return jsonify({'status': 'success', 'message': f'Device {device} set to {status.upper()}'})
        else:
            return jsonify({'status': 'error', 'message': 'Invalid status. Use ON or OFF.'}), 400
    else:
        return jsonify({'status': 'error', 'message': f'Device {device} not found.'}), 404

@app.route('/floor_plan')
def floor_plan():
    if logged_in:
        return render_template('floor_plan.html')
    else:
        return redirect(url_for('login_form'))

if __name__ == '__main__':
    print(f"Server listening on {SERVER_HOST}:{SERVER_PORT} (Flask)")
    print(f"Accessible via No-IP hostname: {NO_IP_HOSTNAME}:{SERVER_PORT} (if port forwarding and DNS are set up correctly)")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=True)
