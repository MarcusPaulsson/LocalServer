import requests
import json
import time
from datetime import datetime, timedelta, timezone

def get_electricity_price(price_area="SE3"):
    """Fetches the current electricity prices for a given price area."""
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

if __name__ == "__main__":
    price_area = "SE3"  # You can change this to your desired price area

    while True:
        electricity_data = get_electricity_price(price_area)
        print_concise_data(electricity_data)
        time.sleep(30)