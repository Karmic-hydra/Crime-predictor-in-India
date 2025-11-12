import sqlalchemy
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base # Correct import
from geoalchemy2 import Geometry # This will work now

# --- 1. Database Connection Setup ---
DATABASE_URL = "postgresql://postgres:noeSage05$@localhost/crime_predictor"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base() # Correct way to call it

# --- 2. Define the Crime Table ---
class Crime(Base):
    __tablename__ = "crimes"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # From your CSV
    state = Column(String, index=True)
    district = Column(String, index=True)
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
    
    # The special PostGIS column
    location = Column(Geometry(geometry_type='POINT', srid=4326), index=True)

# --- 3. Create the Table in the Database ---
def create_tables():
    print("Connecting to database and creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully (if they didn't exist).")

# This allows us to run `python models.py` to create the tables
if __name__ == "__main__":
    # First, you must manually create the 'crime_predictor' DB in psql
    # And run: CREATE EXTENSION postgis;
    create_tables()