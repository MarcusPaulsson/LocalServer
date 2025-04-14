import sqlite3
import time
import psutil
import datetime

DATABASE_NAME = 'server_data.db'
MAX_ENTRIES = 200

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

def main():
    """Main function to create the table and continuously store server data, keeping only the last 200 entries."""
    create_table()
    print(f"Storing server data every 10 seconds in '{DATABASE_NAME}'. Keeping only the last {MAX_ENTRIES} entries. Press Ctrl+C to stop.")
    try:
        while True:
            server_info = fetch_server_info()
            store_server_data(server_info)
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Stored data: CPU={server_info['cpu_percent']}%,"
                  f" Mem={server_info['memory_percent']}%,"
                  f" Disk={server_info['disk_percent']}%")
            time.sleep(10)
    except KeyboardInterrupt:
        print("\nData collection stopped.")

if __name__ == "__main__":
    main()