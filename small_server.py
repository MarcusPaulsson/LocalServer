from flask import Flask, request, redirect, url_for, render_template, jsonify
import os
import datetime
import time
import importlib
import psutil
import sqlite3
import requests  # Import the requests library


# --- Configuration for Battery Control ---
LOW_BATTERY_THRESHOLD = 35
HIGH_BATTERY_THRESHOLD = 80
BATTERY_CHECK_INTERVAL_SECONDS = 180  # Check battery status every 60 seconds
AUTOMATIC_CHARGING_ENABLED = True  # Enable/disable automatic charging control

# --- Configuration ---
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 80
NO_IP_HOSTNAME = 'your_ddns.net'  # Replace with your No-IP hostname if used
DATABASE_NAME = 'server_data.db'
SHELLEY_IP = "192.168.1.103"  # Define Shelly IP here

# --- Encryption & User Config ---
from key import ENCRYPTION_KEY, USERS
from cryptography.fernet import Fernet
fernet = Fernet(ENCRYPTION_KEY)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Replace with a persistent key for production
logged_in = False  # For demo purposes only
app.start_time = time.time()  # Start time for uptime
last_plug_state = None # Track the last commanded state of the plug

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

def get_shelly_status():
    """Fetches the current status of the Shelly device."""
    try:
        status_url = f"http://{SHELLEY_IP}/relay/0/status"
        response = requests.get(status_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {"ison": data.get("ison"), "success": True}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Shelly status: {e}")
        return {"ison": None, "success": False, "error": str(e)}

def toggle_shelly_relay(turn_on):
    """Toggles the Shelly relay on or off."""
    try:
        turn = "on" if turn_on else "off"
        control_url = f"http://{SHELLEY_IP}/relay/0?turn={turn}"
        response = requests.get(control_url, timeout=5)
        response.raise_for_status()
        return {"success": True}
    except requests.exceptions.RequestException as e:
        print(f"Error controlling Shelly: {e}")
        return {"success": False, "error": str(e)}

def get_time():
    now = datetime.datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    return current_time

def get_uptime():
    uptime = time.time() - app.start_time
    return int(uptime)

def format_uptime(seconds):
    days = seconds // (3600 * 24)
    hours = (seconds % (3600 * 24)) // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    parts = []
    if days > 0:
        parts.append(f"{days} days")
    if hours > 0:
        parts.append(f"{hours} hours")
    if minutes > 0:
        parts.append(f"{minutes} minutes")
    parts.append(f"{seconds} seconds")
    return ", ".join(parts)

def get_weather_linkoping():
    url = "https://api.met.no/weatherapi/nowcast/2.0/complete?lat=58.41&lon=15.62"
    headers = {"User-Agent": "SmartHomeDashboard/1.0 (example@example.com)"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data and data.get("properties") and data.get("properties").get("timeseries"):
            current_entry = data["properties"]["timeseries"][0]
            time_str = current_entry.get("time")
            details = current_entry.get("data").get("instant").get("details")
            formatted_time = datetime.datetime.fromisoformat(time_str.replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M:%S')
            temperature = details.get("air_temperature")
            wind_speed = details.get("wind_speed")
            return {
                "time": formatted_time,
                "temperature": temperature,
                "wind_speed": wind_speed,
                "success": True,
            }
        else:
            return {"success": False, "error": "Could not parse weather data"}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return {"success": False, "error": str(e)}

def get_battery_status():
    """Retrieves the current battery status."""
    try:
        battery = psutil.sensors_battery()
        if battery:
            percent = battery.percent
            is_charging = battery.power_plugged
            seconds_left = battery.secsleft
            return {
                "percent": percent,
                "is_charging": is_charging,
                "seconds_left": seconds_left,
                "success": True
            }
        else:
            return {"success": False, "error": "No battery information available."}
    except Exception as e:
        return {"success": False, "error": f"Could not retrieve battery information: {e}"}

def check_and_control_battery_charging():
    """Checks battery level and controls the charger plug if automatic charging is enabled."""
    global last_plug_state
    if AUTOMATIC_CHARGING_ENABLED:
        battery_info = get_battery_status()
        if battery_info["success"]:
            percent = battery_info["percent"]
            is_charging = battery_info["is_charging"]

            if percent < LOW_BATTERY_THRESHOLD:
                print(f"Battery low ({percent}%), turning charger ON.")
                toggle_shelly_relay(True)
                last_plug_state = "on"
            elif percent > HIGH_BATTERY_THRESHOLD:
                print(f"Battery high ({percent}%), turning charger OFF.")
                toggle_shelly_relay(False)
                last_plug_state = "off"
            else:
                print(f"Battery: {percent}%, Charging: {is_charging}, Plug state: {last_plug_state}")
        else:
            print(f"Error getting battery status for automatic charging: {battery_info.get('error')}")

def battery_monitor_loop():
    """Runs the battery monitoring and control loop in the background."""
    while True:
        check_and_control_battery_charging()
        time.sleep(BATTERY_CHECK_INTERVAL_SECONDS)

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
                seconds_left = battery_status.get("seconds_left")
                if seconds_left is not None and seconds_left != psutil.POWER_TIME_UNKNOWN and seconds_left != psutil.POWER_TIME_UNLIMITED:
                    minutes, seconds = divmod(seconds_left, 60)
                    hours, minutes = divmod(minutes, 60)
                    battery_time_left = f"{hours}:{minutes:02}:{seconds:02}"
                elif seconds_left == psutil.POWER_TIME_UNLIMITED:
                    battery_time_left = "Unlimited (Plugged In)"
            else:
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
            battery_error=battery_status.get("error") if not battery_status["success"] else None
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

@app.route('/time')
def get_time_route():
    return jsonify({'time': get_time()})

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
    if action == "on":
        result = toggle_shelly_relay(True)
    elif action == "off":
        result = toggle_shelly_relay(False)
    else:
        return "Invalid action", 400

    # After manual toggle, update the last known plug state
    shelly_status = get_shelly_status()
    if shelly_status["success"]:
        global last_plug_state
        last_plug_state = "on" if shelly_status["ison"] else "off"

    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    print(f"Server listening on {SERVER_HOST}:{SERVER_PORT} (Flask)")
    print(f"Accessible via No-IP hostname: {NO_IP_HOSTNAME}:{SERVER_PORT} (if port forwarding and DNS are set up correctly)")

    import threading
    battery_thread = threading.Thread(target=battery_monitor_loop, daemon=True)
    battery_thread.start()

    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=True)