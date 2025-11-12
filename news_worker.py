import os
import sys
import time
from datetime import datetime
import httpx
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from newsapi import NewsApiClient
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
import torch

# --- 1. CONFIGURATION (EDIT THESE!) ---
# Get this from https://newsapi.org
NEWS_API_KEY = "988d19b7a38c49298a3a80e0914791e4"

# This must match the SECRET_API_KEY in your main.py
BACKEND_API_KEY = "hvgiec56w5tai1vl6k388iubink2ww"

# The URL of your running FastAPI server
BACKEND_URL = "http://127.0.0.1:8000/add_crime"

# Search settings
CITY_NAME = "Bengaluru" # We'll use this to geocode
SEARCH_KEYWORDS = [
    '"crime" OR "theft" OR "assault" OR "murder" OR "robbery" OR "arrest"',
    'AND ("Bengaluru" OR "Bangalore")',
]
NEWS_QUERY = ' '.join(SEARCH_KEYWORDS)

# File to store processed URLs to avoid duplicates
PROCESSED_URLS_FILE = "processed_urls.txt"
# ----------------------------------------

# --- 2. INITIALIZE ALL SERVICES ---

# Initialize NewsAPI client
try:
    newsapi = NewsApiClient(api_key=NEWS_API_KEY)
except Exception as e:
    print(f"Error initializing NewsAPI. Check your API key. Error: {e}")
    sys.exit(1)

# Initialize Geocoder
geolocator = Nominatim(user_agent="crime_predictor_worker_v1")

# Initialize NLP Pipeline for Named Entity Recognition (NER)
# This finds location names in the news text
print("--- Loading NLP Model (dslim/bert-base-NER)... ---")
print("This may take a few minutes on first run.")
try:
    tokenizer = AutoTokenizer.from_pretrained("dslim/bert-base-NER")
    model = AutoModelForTokenClassification.from_pretrained("dslim/bert-base-NER")
    # Use 'cuda' if you have a GPU, otherwise 'cpu'
    device = 0 if torch.cuda.is_available() else -1 
    nlp_pipeline = pipeline("ner", model=model, tokenizer=tokenizer, device=device)
    print("--- NLP Model loaded successfully. ---")
except Exception as e:
    print("--- ERROR: Could not load NLP model. ---")
    print("Make sure you have an internet connection and 'transformers' and 'torch' are installed.")
    print(f"Error: {e}")
    sys.exit(1)


# --- 3. HELPER FUNCTIONS ---

def load_processed_urls():  # sourcery skip: collection-builtin-to-comprehension
    """Loads URLs we've already processed to avoid duplicates."""
    if not os.path.exists(PROCESSED_URLS_FILE):
        return set()
    with open(PROCESSED_URLS_FILE, 'r') as f:
        return set(line.strip() for line in f)

def save_processed_url(url):
    """Saves a new URL to our processed file."""
    with open(PROCESSED_URLS_FILE, 'a') as f:
        f.write(url + "\n")

def get_location_from_text(text):
    """Uses NLP to extract the first 'LOC' (Location) entity from text."""
    try:
        ner_results = nlp_pipeline(text)

        # Combine grouped entities (e.g., "MG", "Road" -> "MG Road")
        locations = []
        current_loc = ""
        for entity in ner_results:
            if entity['entity'] == 'B-LOC':  
                if current_loc: locations.append(current_loc)
                current_loc = entity['word']
            elif entity['entity'] == 'I-LOC': 
                
                current_loc += entity['word'].replace('##', '') if entity['word'].startswith('##') else f" {entity['word']}"
        if current_loc: locations.append(current_loc)

        return locations[0] if locations else None
    except Exception as e:
        print(f"NLP processing error: {e}")
        return None

def geocode_location(location_name):
    """Converts a location name (e.g., "Koramangala") to (lat, lon)."""
    try:
        # We add the city name to help the geocoder
        full_query = f"{location_name}, {CITY_NAME}, India"
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
                print(f"--- SUCCESS: Added new crime to database: {crime_data['crime_type']} ---")
            else:
                print(f"--- ERROR: Backend failed. Status: {response.status_code}, Response: {response.text} ---")
                
    except httpx.RequestError as e:
        print(f"--- ERROR: Could not connect to backend at {BACKEND_URL}. Is it running? ---")
        print(f"Error: {e}")

def run_news_cycle():
    """Main function to fetch, process, and post news."""
    print(f"\n[{datetime.now()}] --- Running new cycle. Fetching news... ---")
    processed_urls = load_processed_urls()
    
    try:
        # 1. Fetch news from the last 30 minutes
        articles = newsapi.get_everything(
            q=NEWS_QUERY,
            language='en',
            sort_by='publishedAt',
            page_size=20 # Check the 20 most recent articles
        )
    except Exception as e:
        print("--- ERROR: Could not fetch from NewsAPI. Check key or quota. ---")
        print(f"Error: {e}")
        return

    print(f"Found {articles['totalResults']} total articles. Processing {len(articles['articles'])} most recent...")
    
    new_crimes_found = 0
    
    for article in articles['articles']:
        url = article['url']
        
        # 2. Check for duplicates
        if url in processed_urls:
            continue
            
        print(f"\nProcessing new article: {article['title']}")
        
        # 3. Extract location using NLP
        text_to_process = article['title'] + ". " + (article['description'] or "")
        location_name = get_location_from_text(text_to_process)
        
        if not location_name:
            print("No specific location found in text. Skipping.")
            save_processed_url(url) # Save to skip next time
            continue
            
        # 4. Geocode the location name
        lat, lon = geocode_location(location_name)
        
        if lat is None or lon is None:
            print("Geocoding failed. Skipping.")
            save_processed_url(url) # Save to skip next time
            continue
            
        # 5. We have a new crime! Prepare and post it.
        new_crimes_found += 1
        
        # Parse timestamp
        dt_obj = datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00'))

        # Simple crime type classification (you can make this smarter)
        crime_type = "crime incident"
        if 'theft' in article['title'].lower(): crime_type = 'theft'
        if 'robbery' in article['title'].lower(): crime_type = 'robbery'
        if 'assault' in article['title'].lower(): crime_type = 'assault'
        if 'murder' in article['title'].lower(): crime_type = 'murder'

        # Build the payload for our API
        crime_data = {
            "crime_type": crime_type,
            "latitude": lat,
            "longitude": lon,
            "year": dt_obj.year,
            "days": dt_obj.strftime('%A'), # e.g., "Saturday"
            "hour_of_day": dt_obj.hour,
            "minute": dt_obj.minute
        }
        
        # 6. Post to our backend
        post_crime_to_backend(crime_data)
        
        # 7. Save to processed list
        save_processed_url(url)
        
        # Be nice to the geocoder API
        time.sleep(1) 

    print(f"--- Cycle complete. Found and processed {new_crimes_found} new crimes. ---")

# --- 4. MAIN WORKER LOOP ---
if __name__ == "__main__":
    if NEWS_API_KEY == "PASTE_YOUR_NEWSAPI_KEY_HERE" or BACKEND_API_KEY == "PASTE_YOUR_SECRET_API_KEY_HERE":
        print("--- FATAL ERROR: API keys not set! ---")
        print("Please edit 'news_worker.py' and add your keys.")
    else:
        while True:
            run_news_cycle()
            sleep_duration = 30 * 60 # 30 minutes
            print(f"Sleeping for {sleep_duration / 60} minutes...")
            time.sleep(sleep_duration)
