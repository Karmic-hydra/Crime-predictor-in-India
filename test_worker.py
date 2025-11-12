import httpx
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from datetime import datetime
import time

# --- 1. CONFIGURATION (EDIT THIS!) ---
# This must match the SECRET_API_KEY in your main.py
BACKEND_API_KEY = "hvgiec56w5tai1vl6k388iubink2ww"
BACKEND_URL = "http://127.0.0.1:8000/add_crime"
# ----------------------------------------

# Initialize Geocoder
geolocator = Nominatim(user_agent="crime_predictor_worker_v1")

def geocode_location(location_name):
    """Converts a location name (e.g., "Koramangala") to (lat, lon)."""
    try:
        full_query = f"{location_name}, Bengaluru, India"
        if location := geolocator.geocode(full_query, timeout=10):
            print(f"Geocoded '{location_name}' to ({location.latitude}, {location.longitude})")
            return location.latitude, location.longitude
        else:
            print(f"Could not geocode '{location_name}'")
            return None, None

    except GeocoderTimedOut:
        print("Geocoder timed out. Skipping.")
        return None, None
    except Exception as e:
        print(f"Geocoder error: {e}")
        return None, None

def post_crime_to_backend(crime_data):
    """Sends the new crime data to our FastAPI backend."""
    headers = {'x-api-key': BACKEND_API_KEY, 'Content-Type': 'application/json'}
    try:
        with httpx.Client() as client:
            response = client.post(BACKEND_URL, json=crime_data, headers=headers, timeout=20)
            
            if response.status_code == 200:
                print(f"\n--- !!! TEST SUCCESSFUL !!! ---")
                print(f"Added new crime to database: {crime_data['crime_type']}")
            else:
                print(f"--- ERROR: Backend failed. Status: {response.status_code}, Response: {response.text} ---")
                
    except httpx.RequestError as e:
        print(f"--- ERROR: Could not connect to backend at {BACKEND_URL}. Is it running? ---")
        print(f"Error: {e}")

# --- MAIN TEST FUNCTION ---
def run_test():
    print("--- Starting Test Worker ---")
    
    # 1. Let's invent a crime in a real neighborhood
    fake_location_name = "Koramangala"
    print(f"Testing with fake crime in: {fake_location_name}")
    
    # 2. Geocode the location
    lat, lon = geocode_location(fake_location_name)
    
    if lat is None or lon is None:
        print("Geocoding failed. Cannot complete test.")
        return
        
    # 3. Prepare the fake crime data
    now = datetime.now()
    crime_data = {
        "crime_type": "TEST CRIME (THEFT)",
        "latitude": lat,
        "longitude": lon,
        "year": now.year,
        "days": now.strftime('%A'),
        "hour_of_day": now.hour,
        "minute": now.minute
    }
    
    # 4. Post to our backend
    post_crime_to_backend(crime_data)

# --- RUN THE TEST ---
if __name__ == "__main__":
    if BACKEND_API_KEY == "PASTE_YOUR_SECRET_API_KEY_HERE":
        print("--- FATAL ERROR: API key not set! ---")
    else:
        run_test()
