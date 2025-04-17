from flask import Flask, request, redirect, url_for, render_template, jsonify
import os
import time
import requests  
import threading
from datetime import *

# --- Configuration for Battery Control ---
LOW_BATTERY_THRESHOLD = 35
HIGH_BATTERY_THRESHOLD = 80
BATTERY_CHECK_INTERVAL_SECONDS = 30  # Check battery status every 2 seconds
AUTOMATIC_CHARGING_ENABLED = True  # Enable/disable automatic charging control

# --- Charger Information ---
ENERGY_PER_CHARGE_CYCLE_WH = 27.47  # Measured energy per full charge cycle 35-80

# --- Encryption & User Config ---
from key import ENCRYPTION_KEY, USERS
from cryptography.fernet import Fernet
fernet = Fernet(ENCRYPTION_KEY)

# --- Helper Functions for Dynamic Constants, assume that all non defined methods comes from here
from helper_server import *

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Replace with a persistent key for production
logged_in = False  # For demo purposes only
app.start_time = time.time()  # Start time for uptime
last_plug_state = None  # Track the last commanded state of the plug
charging_start_time = None
total_energy_charged_wh = 0  # To accumulate energy over charging cycles
last_battery_percent = None
last_check_time = None

def check_and_control_battery_charging():
        """Checks battery level and controls the charger plug if automatic charging is enabled."""
        global last_plug_state, charging_start_time, total_energy_charged_wh, last_battery_percent, last_check_time
        battery_info = get_battery_status()
        if battery_info["success"]:
            percent = battery_info["percent"]
            is_charging = battery_info["is_charging"]
            current_time = time.time()
            if percent < LOW_BATTERY_THRESHOLD and not is_charging and last_plug_state != "on":
                print(f"Battery low ({percent}%), turning charger ON.")
                toggle_shelly_relay(True)
                last_plug_state = "on"
                charging_start_time = current_time
                last_battery_percent = percent
            elif percent > HIGH_BATTERY_THRESHOLD and is_charging  and last_battery_percent < HIGH_BATTERY_THRESHOLD:
                print(f"Battery high ({percent}%), turning charger OFF. Adding {ENERGY_PER_CHARGE_CYCLE_WH:.2f} Wh.")
                toggle_shelly_relay(False)
                last_plug_state = "off"
                total_energy_charged_wh += ENERGY_PER_CHARGE_CYCLE_WH
                charging_start_time = None
                last_battery_percent = None
            elif is_charging and charging_start_time is None:
                charging_start_time = current_time
                last_battery_percent = percent
            elif not is_charging:
                charging_start_time = None
                last_battery_percent = None
            last_check_time = current_time
            print(f"Battery: {percent}%, Charging: {is_charging}, Plug state: {last_plug_state}, Energy charged (approx): {total_energy_charged_wh:.2f} Wh")
        else:
            print(f"Error getting battery status for automatic charging: {battery_info.get('error')}")

def battery_monitor_loop():
    """Runs the battery monitoring and control loop in the background."""
    global last_check_time
    last_check_time = time.time() # Initialize last check time
    while True:
        check_and_control_battery_charging()
        time.sleep(BATTERY_CHECK_INTERVAL_SECONDS)

def get_uptime():
    return int(time.time() - app.start_time)

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
        shelly_status = get_shelly_status()
        weather_data = get_weather_linkoping()
        recent_server_data = get_recent_server_data()
        uptime = get_uptime()
        current_time = get_time()
        battery_status = get_battery_status()

        battery_percent = None
        battery_charging = None
        battery_time_left = None

        if battery_status["success"]:
            battery_percent = battery_status["percent"]
            battery_charging = battery_status["is_charging"]
            if not battery_charging:
                battery_time_left = "Charging"

        return render_template(
            'dashboard.html',
            current_temperature=current_temperature,
            server_info=latest_server_info,
            shelly_status=shelly_status,
            weather=weather_data,
            recent_server_data=recent_server_data,
            uptime=format_uptime(uptime),
            current_time=current_time,
            battery_percent=battery_percent,
            battery_charging=battery_charging,
            battery_time_left=battery_time_left,
            battery_error=battery_status.get("error") if not battery_status["success"] else None,
            energy_charged=f"{total_energy_charged_wh:.2f}" # Pass the energy to the template
        )
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

@app.route('/uptime')
def get_uptime_route():
    return jsonify({'uptime': get_uptime()})

@app.route('/floor_plan')
def floor_plan():
    if logged_in:
        return render_template('floor_plan.html')
    else:
        return redirect(url_for('login_form'))

@app.route('/toggle_charger/<action>', methods=['POST'])
def toggle_charger(action):
    if not logged_in:
        return redirect(url_for('login_form'))  # Or handle unauthorized access differently
    global last_plug_state, charging_start_time, total_energy_charged_wh, last_battery_percent
    if action == "on":
        result = toggle_shelly_relay(True)
        if result["success"]:
            last_plug_state = "on"
            if charging_start_time is None and not get_battery_status()["is_charging"]:
                charging_start_time = time.time()
    elif action == "off":
        result = toggle_shelly_relay(False)
        if result["success"]:
            last_plug_state = "off"
            battery_status = get_battery_status()
            if charging_start_time is not None and battery_status["success"] and battery_status["percent"] >= HIGH_BATTERY_THRESHOLD and last_battery_percent is not None and last_battery_percent < HIGH_BATTERY_THRESHOLD:
                print(f"Manual turn off at {battery_status['percent']}%. Adding {ENERGY_PER_CHARGE_CYCLE_WH:.2f} Wh.")
                charging_start_time = None
    else:
        return "Invalid action", 400
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    battery_thread = threading.Thread(target=battery_monitor_loop, daemon=True)
    battery_thread.start()
    electricity_thread = threading.Thread(target=electricity_price_loop, daemon=True)
    electricity_thread.start()

    app.run(host="0.0.0.0", port=80, debug=True)
    