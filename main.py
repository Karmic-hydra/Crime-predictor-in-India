import pandas as pd
import joblib
import h3
from fastapi import FastAPI, Depends, HTTPException, Header, status
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import func
from geoalchemy2.shape import from_shape
from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID
from models import SessionLocal, Crime, engine # Import from models.py
from fastapi.middleware.cors import CORSMiddleware
import subprocess # NEW: To run external scripts
import sys # NEW: To find the python executable
import os # NEW: To find the python executable

# --- NEW: Import Scheduler ---
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# --- 1. CONFIGURATION & SECRET KEY ---
# !!! CHANGE THIS to a long, random string !!!
SECRET_API_KEY = "hvgiec56w5tai1vl6k388iubink2ww" 

# --- 2. LOAD MODELS & ENCODERS ---
print("--- Loading model and encoders... ---")
# We make these global so the scheduler can reload them
model = None
h3_encoder = None
day_encoder = None

def load_models():
    global model, h3_encoder, day_encoder
    try:
        model = joblib.load('crime_model.joblib')
        h3_encoder = joblib.load('h3_index_encoder.joblib')
        day_encoder = joblib.load('day_encoder.joblib')
        print("Models and encoders loaded/reloaded successfully.")
    except FileNotFoundError:
        print("--- FATAL ERROR: Model files not found. ---")
        print("Please run 'train_model.py' first.")
        exit()

load_models() # Load models on initial startup

# --- 3. CREATE FASTAPI APP ---
app = FastAPI(
    title="Crime Predictor API",
    description="API for live crime risk prediction and historical hotspot data."
)

# --- 4. ADD CORS MIDDLEWARE ---
origins = [
    "http://localhost",
    "http://localhost:5500",
    "http://127.0.0.1",
    "http://127.0.0.1:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 5. DATABASE DEPENDENCY ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 6. PYDANTIC REQUEST MODELS ---
class PredictionRequest(BaseModel):
    latitude: float
    longitude: float

# NEW: Model for adding a crime from our worker
class NewCrime(BaseModel):
    crime_type: str
    latitude: float
    longitude: float
    year: int
    days: str
    hour_of_day: int
    minute: int

# --- 7. AUTOMATED RE-TRAINING TASK ---

def run_training_script():
    """
    Runs the 'train_model.py' script as a separate process
    and reloads the models in this server.
    """
    print("\n--- [SCHEDULER]: Starting nightly re-training... ---")
    try:
        # Find the python executable for the current venv
        python_executable = os.path.join(sys.prefix, 'bin', 'python') # For Linux/macOS
        if not os.path.exists(python_executable):
            python_executable = os.path.join(sys.prefix, 'Scripts', 'python.exe') # For Windows

        # Run the script
        subprocess.run([python_executable, "train_model.py"], check=True)
        print("--- [SCHEDULER]: 'train_model.py' executed successfully. ---")
        
        # Reload the models into the running server
        print("--- [SCHEDULER]: Reloading new models... ---")
        load_models()
        print("--- [SCHEDULER]: Nightly re-training complete. ---")
        
    except Exception as e:
        print(f"--- [SCHEDULER]: ERROR during re-training: {e} ---")

# --- 8. START THE SCHEDULER ---
scheduler = BackgroundScheduler()
# Run at 3:00 AM every night
scheduler.add_job(run_training_script, CronTrigger(hour=3, minute=0))
scheduler.start()
print("--- Nightly re-training scheduler started. Will run at 3:00 AM. ---")


# --- 9. ENDPOINT 1: LIVE RISK PREDICTION ---
@app.post("/predict_risk")
async def predict_risk(request: PredictionRequest):
    H3_RESOLUTION = 9 
    now = datetime.now()
    current_hour = now.hour
    current_day = now.strftime('%A') 

    # Use the v3 function name that we verified
    h3_index = h3.latlng_to_cell(request.latitude, request.longitude, H3_RESOLUTION)

    try:
        h3_encoded = h3_encoder.transform([h3_index])[0]
        day_encoded = day_encoder.transform([current_day])[0]
        
        features = [[h3_encoded, day_encoded, current_hour]]
        probabilities = model.predict_proba(features)[0]
        
        prob_high = probabilities[2] 
        prob_medium = probabilities[1]

        if prob_high > 0.7:
            risk = "red"
            sureness = prob_high
        elif prob_medium > 0.3:
            risk = "yellow"
            sureness = prob_medium
        else:
            risk = "green"
            sureness = probabilities[0]

        return {
            "risk_level": risk,
            "sureness_score": float(sureness),
            "h3_index": h3_index
        }
        
    except ValueError as e:
        return {
            "risk_level": "green",
            "sureness_score": 1.0,
            "h3_index": h3_index,
            "error": "Location or day not found in model, defaulting to low risk."
        }

# --- 10. ENDPOINT 2: HISTORICAL HOTSPOTS ---
@app.get("/get_hotspots")
async def get_hotspots(lat: float, lon: float, radius_km: float = 2.0, db: Session = Depends(get_db)):
    
    radius_meters = radius_km * 1000
    user_point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
    
    query = db.query(
        Crime.latitude,
        Crime.longitude,
        Crime.crime_type,
        Crime.days,
        Crime.hour_of_day
    ).filter(
        ST_DWithin(Crime.location, user_point, radius_meters)
    ).limit(500)
    
    hotspots = query.all()
    # Convert query results to a list of dictionaries
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

# --- 11. NEW ENDPOINT: ADD CRIME FROM WORKER ---
@app.post("/add_crime")
async def add_crime(
    crime: NewCrime, 
    x_api_key: str = Header(None), 
    db: Session = Depends(get_db)
):
    """
    A secure endpoint for our news_worker.py to add new, 
    confirmed crimes to the database.
    """
    # 1. Check the secret API key
    if x_api_key != SECRET_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API Key"
        )
        
    # 2. Create the PostGIS location string
    point_geom = f'SRID=4326;POINT({crime.longitude} {crime.latitude})'
    
    # 3. Create the new Crime database object
    new_crime_db = Crime(
        state="Unknown", # We can improve this later
        district="Unknown", # We can improve this later
        year=crime.year,
        crime_type=crime.crime_type,
        count=1.0, # One new crime
        days=crime.days,
        hour_of_day=crime.hour_of_day,
        minute=crime.minute,
        latitude=crime.latitude,
        longitude=crime.longitude,
        location=point_geom
    )
    
    # 4. Add to database and commit
    try:
        db.add(new_crime_db)
        db.commit()
        return {"status": "success", "message": f"New crime '{crime.crime_type}' added to database."}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving to database: {e}"
        )

# --- 12. Root Endpoint ---
@app.get("/")
def read_root():
    return {"message": "Crime Predictor API is running. Go to /docs to see endpoints."}