import os
import requests
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Database dependencies
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from geoalchemy2.functions import ST_MakePoint
from models import NewsArticle, Base

# External libraries
from geopy.geocoders import Nominatim

# --- CONFIGURATION ---

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')
GNEWS_API_KEY = os.getenv('GNEWS_API_KEY', '005d7223f2f4f039f14c85dce0e5f332')
API_SECRET_KEY = os.getenv('API_SECRET_KEY')
LANGUAGE = os.getenv('NEWS_LANGUAGE', 'en')
PRUNE_DAYS = 30  # Keep articles for 30 days (shorter rolling window for relevance)

# Crime-related keywords for filtering (same as fetch_news.py)
CRIME_KEYWORDS = [
    'murder', 'robbery', 'theft', 'assault', 'burglary', 'kidnapping',
    'fraud', 'scam', 'crime', 'criminal', 'police', 'arrest', 'investigation',
    'violence', 'attack', 'homicide', 'rape', 'molestation', 'harassment',
    'extortion', 'stabbing', 'shooting', 'gang', 'drugs', 'narcotic',
    'smuggling', 'cybercrime', 'hacking', 'domestic violence', 'missing person'
]

# Validate required environment variables
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env file")
if not GNEWS_API_KEY:
    raise ValueError("GNEWS_API_KEY not found in .env file")

# Initialize geocoder (Nominatim for geolocation)
geolocator = Nominatim(user_agent="geospatial-crime-predictor-v2") 

# --- DATABASE SETUP ---

engine = create_engine(DATABASE_URL)
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)


def is_crime_related(text):
    """Check if text contains crime-related keywords."""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in CRIME_KEYWORDS)


def extract_location_from_text(text):
    """
    Extract Bangalore location names from article text.
    Simple keyword-based approach for common Bangalore areas.
    """
    bangalore_areas = [
        'Koramangala', 'Indiranagar', 'Whitefield', 'Marathahalli', 'HSR Layout',
        'BTM Layout', 'Jayanagar', 'MG Road', 'Brigade Road', 'Electronic City',
        'Silk Board', 'Hebbal', 'Yeshwantpur', 'Malleshwaram', 'Rajajinagar',
        'JP Nagar', 'Banashankari', 'Basavanagudi', 'Ulsoor', 'Richmond Town',
        'Sadashivnagar', 'Vasanth Nagar', 'Shivajinagar', 'Yelahanka', 'Sarjapur',
        'Bellandur', 'Kadugodi', 'KR Puram', 'Mahadevapura', 'Bommanahalli'
    ]
    
    text_lower = text.lower() if text else ''
    
    for area in bangalore_areas:
        if area.lower() in text_lower:
            return f"{area}, Bengaluru, Karnataka, India"
    
    # Fallback: if "Bangalore" or "Bengaluru" mentioned but no specific area
    if 'bangalore' in text_lower or 'bengaluru' in text_lower:
        return "Bengaluru, Karnataka, India"
    
    return None


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
    
    # Extract location from title and description
    title = article.get('title', '')
    description = article.get('description', '')
    combined_text = f"{title} {description}"
    
    location_name = extract_location_from_text(combined_text)

    if not location_name:
        return 0, "No Bangalore location found in article"

    try:
        # Geocoding with retry logic
        location = geolocator.geocode(location_name, timeout=10)
        if not location:
            return 0, f"Geocoding failed for {location_name}"

        # Create NewsArticle object
        pub_date_str = article.get('publishedAt', '')
        try:
            # GNews format: 2024-11-14T10:30:00Z
            published_at = datetime.strptime(pub_date_str, '%Y-%m-%dT%H:%M:%SZ')
        except:
            published_at = datetime.now()
        
        new_article = NewsArticle(
            url=article['url'],
            title=article.get('title', 'No title')[:500],  # Truncate if needed
            published_at=published_at,
            location_name=location_name,
            latitude=location.latitude,
            longitude=location.longitude,
            location=ST_MakePoint(location.longitude, location.latitude, srid=4326)
        )
        
        # Save to DB
        session.add(new_article)
        session.commit()
        return 1, f"Saved: {location_name}"

    except IntegrityError:
        session.rollback()
        return 0, f"Duplicate article (URL already exists)"
    except Exception as e:
        session.rollback()
        return 0, f"Error: {str(e)[:100]}"


def fetch_and_save_news():
    """Main function to fetch news from GNews API and save relevant crime articles."""
    session = DBSession()
    
    # Step 1: Prune old data (30-day rolling window)
    prune_old_articles(session)

    # Step 2: Fetch news from GNews API
    url = "https://gnews.io/api/v4/search"
    params = {
        'q': 'Bangalore OR Bengaluru',
        'lang': LANGUAGE,
        'country': 'in',
        'max': 100,
        'apikey': GNEWS_API_KEY
    }
    
    print(f"\n{'='*60}")
    print("NEWS WORKER: Fetching Bangalore news from GNews API")
    print(f"{'='*60}")
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if 'articles' not in data:
            print(f"API Error: {data.get('errors', 'Unknown error')}")
            session.close()
            return
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from GNews API: {e}")
        session.close()
        return

    # Step 3: Filter for crime-related articles
    all_articles = data.get('articles', [])
    crime_articles = []
    
    for article in all_articles:
        title = article.get('title', '')
        description = article.get('description', '')
        combined_text = f"{title} {description}"
        
        if is_crime_related(combined_text):
            crime_articles.append(article)
    
    print(f"✓ Fetched {len(all_articles)} total articles")
    print(f"✓ Found {len(crime_articles)} crime-related articles")
    
    # Step 4: Process and save to database
    saved_count = 0
    skipped_count = 0
    error_count = 0
    
    for article in crime_articles:
        if not article.get('url') or not article.get('publishedAt'):
            skipped_count += 1
            continue
            
        success, message = geolocate_and_save_article(session, article)
        
        if success:
            saved_count += 1
            print(f"  ✓ {message}")
        elif "Duplicate" in message:
            skipped_count += 1
        elif "No Bangalore location" in message:
            skipped_count += 1
        else:
            error_count += 1
            print(f"  ✗ {message}")

    print(f"\n{'='*60}")
    print(f"WORKER RUN COMPLETE")
    print(f"{'='*60}")
    print(f"Total articles fetched: {len(all_articles)}")
    print(f"Crime-related articles: {len(crime_articles)}")
    print(f"Saved to database: {saved_count}")
    print(f"Skipped (duplicates/no location): {skipped_count}")
    print(f"Errors: {error_count}")
    print(f"{'='*60}\n")
    
    session.close()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("CONTEXTUAL NEWS WORKER - GNews API Integration")
    print("="*60)
    print("Configuration:")
    print(f"  - Database: {'Connected' if DATABASE_URL else 'NOT SET'}")
    print(f"  - GNews API: {'Configured' if GNEWS_API_KEY else 'NOT SET'}")
    print(f"  - Prune Days: {PRUNE_DAYS} days rolling window")
    print(f"  - Crime Keywords: {len(CRIME_KEYWORDS)} patterns")
    print(f"  - Loop Interval: 30 minutes")
    print("="*60 + "\n")
    
    # Create the news_articles table if it doesn't exist
    Base.metadata.create_all(engine)
    
    while True:
        try:
            fetch_and_save_news()
        except Exception as e:
            print(f"\n⚠ MAJOR ERROR in worker loop: {e}\n")
            
        print("Worker sleeping for 30 minutes...")
        time.sleep(30 * 60)  # Sleep for 30 minutes