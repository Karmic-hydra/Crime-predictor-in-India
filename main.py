import os
import json
import joblib
import h3
from datetime import datetime, timedelta
from typing import List

# FastAPI and dependencies
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.functions import ST_MakePoint, ST_DWithin, ST_SetSRID, ST_AsGeoJSON
from pydantic import BaseModel
# Import database models
from models import SessionLocal, Crime, NewsArticle, engine, Base # Import NewsArticle here

# --- CONFIGURATION ---

# The API BASE URL is dynamically determined on deployment, but we use 8000 locally
# For production, this list should include your Netlify/Vercel URL
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://your-frontend-domain.com", # Placeholder for Task 5
]

# H3 resolution used for prediction cells (e.g., 8 is ~0.73 sq km)
H3_RESOLUTION = 8 

# --- MODEL AND SCHEDULER (Placeholder for actual execution) ---

# Mock Model/Encoder storage (actual .joblib files would be loaded here)
crime_model = None
h3_index_encoder = None
day_encoder = None

class LocationInput(BaseModel):
    latitude: float
    longitude: float
def load_models():
    """Loads ML models and encoders on startup."""
    global crime_model, h3_index_encoder, day_encoder
    try:
        # NOTE: In a real app, these files would be downloaded from S3/GCS 
        # and loaded into memory on startup.
        print("Loading ML models... (MOCK LOAD)")
        crime_model = True # Mocking a loaded model
        h3_index_encoder = True
        day_encoder = True
        
    except Exception as e:
        print(f"ERROR: Could not load ML models: {e}")
        # In a real deployment, you might let the app crash if models fail to load

def start_scheduler():
    """Placeholder for APScheduler setup (Task 2 logic is now in GitHub Actions)."""
    print("APScheduler logic is intentionally skipped in this local main.py.")
    print("Daily model retraining is handled via GitHub Actions (Task 2).")

# --- DATABASE DEPENDENCY ---

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FASTAPI APP INITIALIZATION ---

app = FastAPI(title="Geospatial Crime Predictor API")

# Initialize CORS Middleware (Crucial fix from earlier!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load models upon application startup
@app.on_event("startup")
async def startup_event():
    # Ensure tables are created (optional, but harmless)
    Base.metadata.create_all(bind=engine)
    load_models()
    start_scheduler() # Just prints status now

# --- API ENDPOINTS ---

@app.get("/get_hotspots")
async def get_hotspots(lat: float, lon: float, radius_km: float = 2.0, db: Session = Depends(get_db)):
    """
    Endpoint 2: Finds historical crime events within a given radius (PostGIS ST_DWithin).
    """
    # Convert km radius to meters for ST_DWithin
    radius_meters = radius_km * 1000
    
    # We use ST_MakePoint and ST_SetSRID to query for points near the user's location
    # The 'location' column in the Crime model is indexed for fast geospatial lookup
    
    # Note: We must specify public.crimes due to the search path issues we fixed earlier.
    query = db.query(
        Crime.latitude, Crime.longitude, Crime.crime_type, Crime.days, Crime.hour_of_day
    ).filter(
        ST_DWithin(
            Crime.location, 
            ST_SetSRID(ST_MakePoint(lon, lat), 4326), # Input Point (lon, lat)
            radius_meters # Radius in meters
        )
    ).limit(500) # Limit to 500 hotspots as per Fragment 4 plan

    hotspots = query.all()
    
    if not hotspots:
        return {"hotspots": []}

    # Format output for the frontend
    formatted_hotspots = [
        {"lat": h.latitude, "lon": h.longitude, "type": h.crime_type} for h in hotspots
    ]
    
    return {"hotspots": formatted_hotspots}


@app.post("/predict_risk")
async def predict_risk(location_data: LocationInput,db: Session = Depends(get_db)):
    """
    Endpoint 1: Predicts real-time risk (0=Low, 1=Medium, 2=High) and performs contextual check.
    """
    lat = location_data.latitude
    lon = location_data.longitude
    if not crime_model:
        raise HTTPException(status_code=503, detail="ML Model not loaded.")

    # 1. Feature Engineering
    current_time = datetime.now()
    day_name = current_time.strftime('%A')
    hour = current_time.hour
    
    h3_index = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    h3_boundary = h3.cell_to_boundary(h3_index)

    # 2. Statistical Prediction (MOCK STEP)
    # In a real app: 
    # features = [h3_index_encoded, day_encoded, hour]
    # statistical_prediction = crime_model.predict([features])[0]
    
    # MOCK LOGIC for demonstration: 
    # Let's say statistical prediction is randomly Medium (1)
    statistical_prediction = 1 
    
    risk_level = {0: "green", 1: "yellow", 2: "red"}.get(statistical_prediction, "green")
    final_risk_code = statistical_prediction

    # --- 3. Contextual Grounding Check (NEW FEATURE) ---
    
    # Check for recent news articles within a 1.5 km radius (1500 meters)
    context_radius_meters = 1500 
    time_window = datetime.now() - timedelta(hours=48) # Look for news in the last 48 hours
    
    context_query = db.query(NewsArticle).filter(
        (NewsArticle.published_at >= time_window) & 
        (
            # Geospatial check for nearby articles
            ST_DWithin(
                NewsArticle.location,
                ST_SetSRID(ST_MakePoint(lon, lat), 4326),
                context_radius_meters
            )
        )
    ).limit(5) # Find up to 5 relevant articles
    
    recent_context = context_query.all()
    context_count = len(recent_context)
    
    # 4. Contextual Adjustment
    contextual_status = "Statistical"
    
    if context_count > 0:
        if final_risk_code == 0: # Low Risk statistically, but recent news found
            final_risk_code = 1  # Escalate to Medium Risk
            risk_level = "yellow"
            contextual_status = f"Contextual Escalation ({context_count} reports)"
        elif final_risk_code in (1, 2): # Medium/High Risk confirmed by news
            contextual_status = f"Contextual Confirmation ({context_count} reports)"
        
    # --- 5. Final Response ---
    
    # Format the contextual information for debugging/display on the frontend
    context_data = [
        {"title": article.title, "link": article.url, "location": article.location_name} 
        for article in recent_context
    ]

    return {
        "risk_level": risk_level,
        "risk_code": final_risk_code,
        "h3_index": h3_index,
        "h3_boundary": h3_boundary, # Sent to frontend to draw the hexagon
        "current_time": current_time.isoformat(),
        "context_status": contextual_status,
        "context_data": context_data,
    }


@app.post("/add_crime")
async def add_crime(secret_key: str, # Placeholder for security check
                db: Session = Depends(get_db)):
    """
    Endpoint 3: Placeholder for adding individual crime reports (currently bypassed by worker).
    """
    # This endpoint is now a placeholder as the worker writes directly to DB.
    if secret_key != "YOUR_STRONG_WORKER_SECRET":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret key")
    
    return {"status": "Endpoint is active but worker uses direct DB access for news_corpus."}