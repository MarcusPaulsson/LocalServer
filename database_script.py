import sqlite3
import time
import psutil
import datetime
import requests
import json
from datetime import datetime, timedelta, timezone
import pandas as pd

DATABASE_NAME = 'server_data.db'
MAX_ENTRIES = 200
PRICE_AREA = "SE3"  # Define the price area

latitude = 58.41  # Latitude of Linköping
longitude = 15.62  # Longitude of Linköping
panel_area = 50  # square meters
panel_efficiency = 0.15  # 15% efficiency
beta = -0.004
T_reference = 25

def create_table():
    """Creates the server_data table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            cpu_percent REAL,
            memory_total INTEGER,
            memory_available INTEGER,
            memory_percent REAL,
            disk_total INTEGER,
            disk_used INTEGER,
            disk_percent REAL
        )
    ''')
    conn.commit()
    conn.close()

def fetch_server_info():
    """Fetches current server information using psutil."""
    cpu_percent = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return {
        'cpu_percent': cpu_percent,
        'memory_total': mem.total,
        'memory_available': mem.available,
        'memory_percent': mem.percent,
        'disk_total': disk.total,
        'disk_used': disk.used,
        'disk_percent': disk.percent
    }

def store_server_data(data):
    """Stores the provided server data into the SQLite database and keeps only the last MAX_ENTRIES."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO server_data (cpu_percent, memory_total, memory_available, memory_percent,
                                    disk_total, disk_used, disk_percent)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (data['cpu_percent'], data['memory_total'], data['memory_available'],
          data['memory_percent'], data['disk_total'], data['disk_used'], data['disk_percent']))
    conn.commit()

    # Delete older entries if the number of rows exceeds MAX_ENTRIES
    cursor.execute(f'''
        DELETE FROM server_data
        WHERE id NOT IN (SELECT id FROM server_data ORDER BY timestamp DESC LIMIT {MAX_ENTRIES})
    ''')
    conn.commit()
    conn.close()



def get_latest_electricity_prices():
    """Retrieves the latest electricity prices from the database."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT time_start, SEK_per_kWh
        FROM electricity_prices
        ORDER BY time_start DESC
        LIMIT 2
    ''')
    results = cursor.fetchall()
    conn.close()
    return results


def create_electricity_table():
    """Creates the electricity_prices table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS electricity_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            time_start TEXT UNIQUE,
            SEK_per_kWh REAL
        )
    ''')
    conn.commit()
    conn.close()

def fetch_electricity_price():
    """Fetches and merges electricity prices for the next 24 hours,
    respecting the API's data availability for the next day."""
    now = datetime.now()
    today_str = now.strftime("%Y/%m-%d")
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%Y/%m-%d")

    today_url = f"https://www.elprisetjustnu.se/api/v1/prices/{today_str}_{PRICE_AREA}.json"
    tomorrow_url = f"https://www.elprisetjustnu.se/api/v1/prices/{tomorrow_str}_{PRICE_AREA}.json"

    today_data = []
    tomorrow_data = []

    try:
        today_response = requests.get(today_url)
        today_response.raise_for_status()
        today_data = today_response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching today's electricity data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding today's electricity JSON: {e}")

    # Only fetch tomorrow's data if the current time is past 1 PM
    if now.hour >= 13:
        try:
            tomorrow_response = requests.get(tomorrow_url)
            tomorrow_response.raise_for_status()
            tomorrow_data = tomorrow_response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching tomorrow's electricity data: {e}")
        except json.JSONDecodeError as e:
            print(f"Error decoding tomorrow's electricity JSON: {e}")
    else:
        print("Tomorrow's electricity prices might not be available yet.")

    merged_data = []
    current_hour = now.hour

    # Add today's prices from the current hour onwards
    for item in today_data:
        item_hour = datetime.fromisoformat(item['time_start']).hour
        if item_hour >= current_hour:
            merged_data.append(item)

    # Add tomorrow's prices for the remaining hours of the 24-hour period
    hours_remaining = 24 - len(merged_data)
    for i in range(min(hours_remaining, len(tomorrow_data))):
        merged_data.append(tomorrow_data[i])

    return merged_data

def store_electricity_data(data):
    """Stores the fetched electricity price data into the SQLite database, avoiding duplicates and keeping only the last MAX_ENTRIES."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    entries_added = 0
    if data:
        for item in data:
            time_start = item.get("time_start")
            sek_per_kwh = item.get("SEK_per_kWh")
            if time_start is not None and sek_per_kwh is not None:
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO electricity_prices (time_start, SEK_per_kWh)
                        VALUES (?, ?)
                    ''', (time_start, sek_per_kwh))
                    conn.commit()
                    entries_added += 1
                except sqlite3.IntegrityError:
                    # Ignore duplicate entries
                    pass

        # Delete older entries if the number of rows exceeds MAX_ENTRIES
        cursor.execute(f'''
            DELETE FROM electricity_prices
            WHERE id NOT IN (SELECT id FROM electricity_prices ORDER BY timestamp DESC LIMIT {MAX_ENTRIES})
        ''')
        conn.commit()
    conn.close()
    return entries_added




def create_solar_table():
    """Creates the solar_data table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solar_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            time_utc TEXT UNIQUE,
            time_local TEXT,
            ghi REAL,
            temperature REAL,
            predicted_power REAL
        )
    ''')
    conn.commit()
    conn.close()



def get_solar_and_temp_forecast(lat, lon, num_hours):
    """Fetches solar irradiance and temperature data from Open-Meteo."""
    base_url = "https://api.open-meteo.com/v1/forecast"
    now_utc = datetime.utcnow()
    end_time_utc = now_utc + timedelta(hours=num_hours)
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["shortwave_radiation", "temperature_2m"],
        "timezone": "Europe/Stockholm",
        "start_date": now_utc.strftime('%Y-%m-%d'),
        "end_date": end_time_utc.strftime('%Y-%m-%d')
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Open-Meteo: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from Open-Meteo: {e}")
        return None



def store_solar_data(data):
    """Stores the solar data into the SQLite database, avoiding duplicates and keeping only the last MAX_ENTRIES."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    entries_added = 0
    if data and 'hourly' in data:
        time_utc_data = data['hourly']['time']
        time_local_data = [pd.to_datetime(t, utc=True).tz_convert('Europe/Stockholm').strftime('%Y-%m-%d %H:%M:%S') for t in time_utc_data]
        ghi_data = data['hourly']['shortwave_radiation']
        temperature_data = data['hourly']['temperature_2m']
        K = panel_efficiency
        predicted_power_data = [panel_area * K * g * (1 + beta * (t - T_reference)) if g > 0 else 0 for g, t in zip(ghi_data, temperature_data)]

        for time_utc, time_local, ghi, temp, power in zip(time_utc_data, time_local_data, ghi_data, temperature_data, predicted_power_data):
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO solar_data (time_utc, time_local, ghi, temperature, predicted_power)
                    VALUES (?, ?, ?, ?, ?)
                ''', (time_utc, time_local, ghi, temp, power))
                conn.commit()
                entries_added += 1
            except sqlite3.IntegrityError:
                # Ignore duplicate entries
                pass

    # Delete older entries if the number of rows exceeds MAX_ENTRIES
    cursor.execute(f'''
        DELETE FROM solar_data
        WHERE id NOT IN (SELECT id FROM solar_data ORDER BY timestamp DESC LIMIT {MAX_ENTRIES})
    ''')
    conn.commit()
    conn.close()
    return entries_added



def main():
    """Main function to create the table and continuously fetch and store solar data."""
    create_solar_table() # Create the solar_data table.
    print(f"Storing solar data every hour in '{DATABASE_NAME}'. Keeping only the last {MAX_ENTRIES} entries. Press Ctrl+C to stop.")

    try:
        while True:
            # Fetch data for the next 72 hours (3 days)
            forecast_data = get_solar_and_temp_forecast(latitude, longitude, 72)
            if forecast_data:
                stored_count = store_solar_data(forecast_data)
                if stored_count > 0:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] Stored {stored_count} new solar data entries.")
                else:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] No new solar data to store.")
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] Failed to fetch solar data.")

            time.sleep(60 * 60)  # Fetch data every hour
    except KeyboardInterrupt:
        print("\nData collection stopped.")



def main():
    """Main function to create the table and continuously store server data, and periodically fetch and print electricity prices."""
    create_table()
    create_electricity_table() # Ensure the table exists
    print(f"Storing server data every 10 seconds in '{DATABASE_NAME}'. Keeping only the last {MAX_ENTRIES} entries. Press Ctrl+C to stop.")
    create_solar_table() # Create the solar_data table.
    print(f"Storing solar data every hour in '{DATABASE_NAME}'. Keeping only the last {MAX_ENTRIES} entries. Press Ctrl+C to stop.")

    try:
        while True:
            server_info = fetch_server_info()
            store_server_data(server_info)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Stored data: CPU={server_info['cpu_percent']}%,"
                  f" Mem={server_info['memory_percent']}%,"
                  f" Disk={server_info['disk_percent']}%", end=" ")

            electricity_data = fetch_electricity_price()

            if electricity_data:
                stored_count = store_electricity_data(electricity_data)
                if stored_count > 0:
                    print(f"| Sparade {stored_count} nya elprisposter.", end=" ")
        

            forecast_data = get_solar_and_temp_forecast(latitude, longitude, 72)
            if forecast_data:
                stored_count = store_solar_data(forecast_data)
                if stored_count > 0:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] Stored {stored_count} new solar data entries.")
                else:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] No new solar data to store.")
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] Failed to fetch solar data.")


            time.sleep(10)
    except KeyboardInterrupt:
        print("\nData collection stopped.")


if __name__ == "__main__":
    main()