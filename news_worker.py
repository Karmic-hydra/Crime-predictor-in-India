import requests
import json
import time
from datetime import datetime, timedelta

# Database dependencies
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from geoalchemy2.functions import ST_MakePoint
from models import NewsArticle, Base # Assuming your models.py is in the same directory

# External libraries (Ensure these are in your requirements.txt)
# from newsapi import NewsApiClient # If you use the official client
from geopy.geocoders import Nominatim
# from transformers import pipeline # For NER, usually loaded once

# --- CONFIGURATION ---

# 1. Load from .env or environment variables (REPLACE THESE PLACEHOLDERS)
# For simplicity, we'll hardcode the DB URL for this script, but use .env in real life.
DATABASE_URL = "postgresql://neondb_owner:npg_wJ0lMpkc4RPe@ep-solitary-paper-a4injs6c.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
NEWS_API_KEY = "988d19b7a38c49298a3a80e0914791e4"
# API_SECRET_KEY = "YOUR_STRONG_WORKER_SECRET" # We are now writing directly to DB, not API
SEARCH_QUERY = 'crime AND (Bengaluru OR India)'
PRUNE_DAYS = 365 # Keep articles for one year

# Initialize geocoder (Nominatim for simple geolocation)
geolocator = Nominatim(user_agent="geospatial-crime-predictor")
# Initialize the Hugging Face NER pipeline (assuming basic setup)
# ner_pipeline = pipeline("ner", model="dbmdz/bert-large-cased-finetuned-conll03-english", grouped_entities=True) 

# --- DATABASE SETUP ---

engine = create_engine(DATABASE_URL)
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)


def prune_old_articles(session):
    """Deletes articles older than PRUNE_DAYS to maintain a rolling corpus."""
    prune_date = datetime.now() - timedelta(days=PRUNE_DAYS)
    
    print(f"--- Pruning articles older than: {prune_date.strftime('%Y-%m-%d')} ---")
    
    # Simple SQLAlchemy delete query
    delete_query = session.query(NewsArticle).filter(NewsArticle.published_at < prune_date)
    count = delete_query.count()
    delete_query.delete(synchronize_session=False)
    
    session.commit()
    print(f"--- Deleted {count} old articles from news_corpus. ---")


def geolocate_and_save_article(session, article):
    """Extracts location from an article and saves it to the database."""
    
    # 1. Fake Location Extraction (since we can't run NER here)
    # In a real setup, you would use:
    # locations = ner_pipeline(article['description'] or article['title'])
    # location_name = locations[0]['word'] 
    
    # TEMPORARY: For demonstration, we'll assume the article mentions "Koramangala"
    location_name = "Koramangala, Bengaluru"

    if not location_name:
        return 0, "No relevant location found."

    try:
        # 2. Geocoding
        location = geolocator.geocode(location_name, timeout=5)
        if not location:
            return 0, f"Geocoding failed for {location_name}"

        # 3. Create NewsArticle object
        new_article = NewsArticle(
            url=article['url'],
            title=article['title'],
            published_at=datetime.strptime(article['publishedAt'], '%Y-%m-%dT%H:%M:%SZ'),
            location_name=location_name,
            latitude=location.latitude,
            longitude=location.longitude,
            # PostGIS point creation (SRID 4326)
            location=ST_MakePoint(location.longitude, location.latitude, srid=4326)
        )
        
        # 4. Save to DB
        session.add(new_article)
        session.commit()
        return 1, f"Saved new article: {location_name}"

    except sqlalchemy.exc.IntegrityError:
        # This catches unique constraint violations (same URL added twice)
        session.rollback()
        return 0, f"Article already exists (URL: {article['url']})"
    except Exception as e:
        session.rollback()
        print(f"Error processing article: {e}")
        return 0, str(e)


def fetch_and_save_news():
    """Main function to fetch news and save relevant articles."""
    session = DBSession()
    
    # Step 1: Prune old data
    prune_old_articles(session)

    # Step 2: Fetch news
    # Using a simple requests call as NewsAPI client requires installation
    url = f"https://newsapi.org/v2/everything?q={SEARCH_QUERY}&language=en&apiKey={NEWS_API_KEY}"
    headers = {'User-Agent': 'CrimePredictor/1.0'}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from API: {e}")
        session.close()
        return

    # Step 3: Process and save
    saved_count = 0
    print(f"Found {len(data.get('articles', []))} articles to check.")
    
    for article in data.get('articles', []):
        if not article.get('url') or not article.get('publishedAt'):
            continue
            
        success, message = geolocate_and_save_article(session, article)
        
        if success:
            saved_count += 1
        # else:
        #     print(f"Skipped article: {message}")

    print(f"--- Run complete. Saved {saved_count} new articles to corpus. ---")
    session.close()


if __name__ == "__main__":
    print("--- Starting Contextual News Worker (30-min loop) ---")
    
    # Create the news_corpus table if it doesn't exist (harmless if run multiple times)
    Base.metadata.create_all(engine)
    
    while True:
        try:
            fetch_and_save_news()
        except Exception as e:
            print(f"MAJOR ERROR in main worker loop: {e}")
            
        print(f"Worker sleeping for 30 minutes...")
        time.sleep(30 * 60) # Sleep for 30 minutes