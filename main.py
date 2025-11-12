import pandas as pd
import joblib
import h3
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker, Session
from geoalchemy2.shape import from_shape
from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID
from models import SessionLocal, Crime, engine # Import from models.py

# --- 1. LOAD MODELS & ENCODERS ---
print("--- Loading model and encoders... ---")
try:
    model = joblib.load('crime_model.joblib')
    h3_encoder = joblib.load('h3_index_encoder.joblib')
    day_encoder = joblib.load('day_encoder.joblib')
    print("Models and encoders loaded successfully.")
except FileNotFoundError:
    print("--- FATAL ERROR: Model files not found. ---")
    print("Please run 'train_model.py' first.")
    exit()

# --- 2. CREATE FASTAPI APP ---
app = FastAPI(
    title="Crime Predictor API",
    description="API for live crime risk prediction and historical hotspot data."
)

# Define which "origins" (websites) are allowed to connect.
# We'll allow your "Live Server" and any others.
origins = [
    "http://localhost",
    "http://localhost:5500",
    "http://127.0.0.1",
    "http://127.0.0.1:5500",
    # Add any other origins if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# --- 3. DATABASE DEPENDENCY ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 4. PYDANTIC REQUEST MODEL ---
# This defines the data we expect from the user for a prediction
class PredictionRequest(BaseModel):
    latitude: float
    longitude: float
    
# --- 5. ENDPOINT 1: LIVE RISK PREDICTION ---
@app.post("/predict_risk")
async def predict_risk(request: PredictionRequest):
    """
    Takes a user's latitude and longitude and returns a 
    predicted risk level (green, yellow, red).
    """
    H3_RESOLUTION = 9 # Must be the same as in training!
    
    # 1. Get current time features
    now = datetime.now()
    current_hour = now.hour
    current_day = now.strftime('%A') # e.g., "Saturday"

    # 2. Convert user's location to H3 index
    h3_index = h3.latlng_to_cell(request.latitude, request.longitude, H3_RESOLUTION)

    try:
        # 3. Encode features for the model
        h3_encoded = h3_encoder.transform([h3_index])[0]
        day_encoded = day_encoder.transform([current_day])[0]
        
        # 4. Create the feature array
        features = [[h3_encoded, day_encoded, current_hour]]
        
        # 5. Get prediction probabilities [prob_low, prob_medium, prob_high]
        probabilities = model.predict_proba(features)[0]
        
        prob_high = probabilities[2] # Probability of class 2 (High)
        prob_medium = probabilities[1] # Probability of class 1 (Medium)

        # 6. Define risk level based on probabilities
        if prob_high > 0.7: # 70% sure it's High risk
            risk = "red"
            sureness = prob_high
        elif prob_medium > 0.3: # 30% sure it's Medium risk
            risk = "yellow"
            sureness = prob_medium
        else:
            risk = "green"
            sureness = probabilities[0] # Probability of class 0 (Low)

        return {
            "risk_level": risk,
            "sureness_score": float(sureness),
            "h3_index": h3_index  
        }
        
    except ValueError as e:
        # This error happens if the H3 index or day was not in the training data
        # We default to "green" (low risk)
        print(f"Prediction error for unknown location/day: {e}")
        return {
            "risk_level": "green",
            "sureness_score": 1.0,
            "h3_index": h3_index,
            "error": "Location or day not found in model, defaulting to low risk."
        }

# --- 6. ENDPOINT 2: HISTORICAL HOTSPOTS ---
@app.get("/get_hotspots")
async def get_hotspots(lat: float, lon: float, radius_km: float = 2.0, db: Session = Depends(get_db)):
    """
    Takes a user's lat/lon and a radius (in km), and returns all
    historical crime data from the database within that radius.
    """
    
    # Convert radius from km to meters
    radius_meters = radius_km * 1000
    
    # Create a PostGIS POINT from the user's lat/lon
    # We set it to 4326, which now matches the database
    user_point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    
    # Query the 'crimes' table
    # This query will now work because both 'location' and 'user_point'
    # are in the same SRID (4326).
    query = db.query(
        Crime.latitude,
        Crime.longitude,
        Crime.crime_type,
        Crime.days,
        Crime.hour_of_day
    ).filter(
        ST_DWithin(Crime.location, user_point, radius_meters)
    ).limit(500) # Limit to 500 results for performance
    
    hotspots = query.all()
    
    # Convert results to a list of dictionaries
    results = [
        {
            "latitude": h.latitude,
            "longitude": h.longitude,
            "crime_type": h.crime_type,
            "day": h.days,
            "hour": h.hour_of_day
        } for h in hotspots
    ]
    
    return {
        "count": len(results),
        "hotspots": results
    }