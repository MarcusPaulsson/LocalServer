import importlib
import sqlite3
from key import DATABASE_NAME
import requests
from datetime import *
import psutil
from key import *
import json
import time
from database_script import *
import pytz

LOCAL_TIMEZONE = 'Europe/Stockholm'

def toggle_shelly_relay(turn_on):
    """Toggles the Shelly relay on or off."""
    try:
        turn = "on" if turn_on else "off"
        control_url = f"http://{SHELLY_PLUG_SERVER_IP}/relay/0?turn={turn}"
        response = requests.get(control_url, timeout=5)
        response.raise_for_status()
        return {"success": True}
    except requests.exceptions.RequestException as e:
        print(f"Error controlling Shelly: {e}")
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

def get_time():
    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    return current_time

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

def get_shelly_status():
    """Fetches the current status of the Shelly device."""
    try:
        status_url = f"http://{SHELLY_PLUG_SERVER_IP}/relay/0"
        print(status_url)
        response = requests.get(status_url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {"ison": data.get("ison"), "success": True}
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Shelly status: {e}")
        return {"ison": None, "success": False, "error": str(e)}



# ------------ constants -----------
def load_constants():
    try:
        import dynamic_constants as dc
        importlib.reload(dc)  # Ensure we get the latest version
        return dc.current_temperature
    except ImportError:
        return 20  # Default value

def write_constants(current_temperature):
    content = (
        f"current_temperature = {current_temperature}\n"
    )
    with open("dynamic_constants.py", "w") as f:
        f.write(content)



# ------- Server ----------------
def get_latest_server_data():
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
            formatted_time = datetime.fromisoformat(time_str.replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M:%S')
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
    


def fetch_electricity_data_from_database():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT time_start, SEK_per_kWh
            FROM electricity_prices
            ORDER BY time_start ASC
        ''')
        data_points = cursor.fetchall()
        return data_points
    except sqlite3.Error as e:
        print(f"\nSQLite Error while fetching electricity data: {e}")
        return []
    finally:
        if conn:
            conn.close()


def fetch_solar_data_from_database():
    """Fetches solar data from the database, ordered by time_local."""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT time_local, ghi, temperature, predicted_power
            FROM solar_data
            ORDER BY time_local ASC
        ''')
        data_points = cursor.fetchall()
        return data_points
    except sqlite3.Error as e:
        print(f"\nSQLite Error while fetching solar data: {e}")
        return []
    finally:
        if conn:
            conn.close()
