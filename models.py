import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry # This will work now

# --- 1. Database Connection Setup ---
# Your cloud connection URL (unchanged)
DATABASE_URL = "postgresql://neondb_owner:npg_wJ0lMpkc4RPe@ep-solitary-paper-a4injs6c.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base() 

# --- 2. Define the Crime Table ---
class Crime(Base):
    __tablename__ = "crimes"
    __table_args__ = {"schema": "public"}
    id = Column(Integer, primary_key=True, index=True)
    
    # From your CSV
    state = Column(String, index=True)
    district = Column(String, index=True) # For Bengaluru, this will be the hotspot name
    year = Column(Integer, index=True)
    crime_type = Column(String, index=True)
    count = Column(Float)
    
    # Generated features
    days = Column(String)
    hour_of_day = Column(Integer)
    minute = Column(Integer)
    
    # Geolocation features
    latitude = Column(Float)
    longitude = Column(Float)
    
    # NEW: Added street_name column
    street_name = Column(String, nullable=True) 
    
    # The special PostGIS column
    location = Column(Geometry(geometry_type='POINT', srid=4326), index=True)


# --- 2b. Define the NEW News Corpus Table for Contextual Grounding ---
class NewsArticle(Base):
    """
    Stores recent news articles and their geolocated mentions for contextual grounding.
    """
    __tablename__ = "news_corpus"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True, index=True)
    
    # Article metadata
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    published_at = Column(sqlalchemy.DateTime, index=True)
    
    # Location data extracted by NER (Named Entity Recognition)
    location_name = Column(String) # e.g., "Koramangala" or "Whitefield"
    
    # Geolocation features
    latitude = Column(Float)
    longitude = Column(Float)
    
    # The geospatial point for fast querying
    location = Column(Geometry(geometry_type='POINT', srid=4326), index=True)


# --- 3. Create the Tables in the Database ---
def create_tables():
    print("Connecting to database and creating tables...")
    # This will now check for both 'crimes' and 'news_corpus'
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully (if they didn't exist).")

if __name__ == "__main__":
    create_tables()