import importlib
import sqlite3
from key import DATABASE_NAME
import requests
import datetime
import psutil
from key import *

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
    now = datetime.datetime.now()
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
    




# ---- power price ------ 
import requests
import json
import time
from datetime import datetime, timedelta, timezone
import threading

def get_electricity_price():
    """Fetches the current electricity prices for SE3."""
    price_area = "SE3"  # Hardcoded price area
    now = datetime.now()
    date_str = now.strftime("%Y/%m-%d")
    url = f"https://www.elprisetjustnu.se/api/v1/prices/{date_str}_{price_area}.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None

def print_concise_data(data):
    """Prints a concise output of the current and next hour's price in SEK."""
    if data and len(data) >= 2:
        cet_timezone = timezone(timedelta(hours=2))
        now_cet = datetime.now(cet_timezone)
        current_hour_start_str = now_cet.strftime("%Y-%m-%dT%H:00:00+02:00")

        current_price = None
        next_price = None

        for item in data:
            if item.get("time_start") == current_hour_start_str:
                current_price = item.get("SEK_per_kWh")
            elif datetime.fromisoformat(item.get("time_start")).astimezone(cet_timezone) == now_cet.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1):
                next_price = item.get("SEK_per_kWh")
                break # Assuming the data is ordered by time

        if current_price is not None:
            print(f"Nu: {current_price:.3f} SEK/kWh", end="")
            if next_price is not None:
                print(f", Nästa timme: {next_price:.3f} SEK/kWh")
            else:
                print()
        elif data:
            # If current hour's data isn't immediately available, print the first entry
            print(f"Snart ({data[0].get('time_start')[11:16]}): {data[0].get('SEK_per_kWh', 'N/A'):.3f} SEK/kWh")

def electricity_price_loop():
    """Continuously fetches and prints electricity prices for SE3."""
    while True:
        electricity_data = get_electricity_price()
        print_concise_data(electricity_data)
        time.sleep(30)

