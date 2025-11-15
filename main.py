import os
import json
import joblib
import h3
import requests
from datetime import datetime, timedelta
from typing import List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# FastAPI and dependencies
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.functions import ST_MakePoint, ST_DWithin, ST_SetSRID, ST_AsGeoJSON
from pydantic import BaseModel
# Import database models
from models import SessionLocal, Crime, NewsArticle, engine, Base

# --- CONFIGURATION ---

# The API BASE URL is dynamically determined on deployment, but we use 8000 locally
# For production, this list should include your Netlify/Vercel URL
ALLOWED_ORIGINS = [
    "*",  # Allow all origins for development (IMPORTANT: Restrict in production!)
]

# H3 resolution used for prediction cells (e.g., 8 is ~0.73 sq km)
H3_RESOLUTION = 8 

# Three-Layer Prediction Weights
WEIGHT_HISTORICAL = 0.2   # Past patterns (2001-2014 data)
WEIGHT_ENVIRONMENTAL = 0.5  # Present-day POI density
WEIGHT_CONTEXTUAL = 0.3     # Recent news (48 hours)

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
        print("Loading XGBoost ML models from disk...")
        crime_model = joblib.load('crime_model.joblib')
        h3_index_encoder = joblib.load('h3_index_encoder.joblib')
        day_encoder = joblib.load('day_encoder.joblib')
        print("✅ XGBoost model and encoders loaded successfully!")
        
    except Exception as e:
        print(f"ERROR: Could not load ML models: {e}")
        print("Make sure you've run train_model.py to generate the .joblib files.")
        # In a real deployment, you might let the app crash if models fail to load

def start_scheduler():
    """Placeholder for APScheduler setup (Task 2 logic is now in GitHub Actions)."""
    print("APScheduler logic is intentionally skipped in this local main.py.")
    print("Daily model retraining is handled via GitHub Actions (Task 2).")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- LAYER 2: ENVIRONMENTAL SCORING (OpenStreetMap POI Analysis) ---

def get_environmental_risk_score(lat: float, lon: float, radius_meters: int = 500):
    """
    Layer 2: Queries OpenStreetMap Overpass API for crime-correlated POIs.
    
    High-risk amenities:
    - Bars, nightclubs, pubs (alcohol-related violence)
    - ATMs (robbery targets)
    - Banks (fraud/theft targets)
    - Late-night establishments
    
    Args:
        lat: Latitude
        lon: Longitude
        radius_meters: Search radius (default 500m)
    
    Returns:
        tuple: (risk_score: int [0-2], poi_count: int, poi_details: dict)
    """
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    # Overpass QL query for crime-correlated POIs
    overpass_query = f"""
    [out:json][timeout:10];
    (
      node["amenity"="bar"](around:{radius_meters},{lat},{lon});
      node["amenity"="nightclub"](around:{radius_meters},{lat},{lon});
      node["amenity"="pub"](around:{radius_meters},{lat},{lon});
      node["amenity"="atm"](around:{radius_meters},{lat},{lon});
      node["amenity"="bank"](around:{radius_meters},{lat},{lon});
      node["shop"="alcohol"](around:{radius_meters},{lat},{lon});
    );
    out body;
    """
    
    try:
        response = requests.post(overpass_url, data={'data': overpass_query}, timeout=12)
        response.raise_for_status()
        data = response.json()
        
        elements = data.get('elements', [])
        poi_count = len(elements)
        
        # Categorize POIs
        poi_breakdown = {
            'bars': 0,
            'nightclubs': 0,
            'atms': 0,
            'banks': 0,
            'alcohol_shops': 0
        }
        
        for element in elements:
            tags = element.get('tags', {})
            amenity = tags.get('amenity', '')
            shop = tags.get('shop', '')
            
            if amenity == 'bar' or amenity == 'pub':
                poi_breakdown['bars'] += 1
            elif amenity == 'nightclub':
                poi_breakdown['nightclubs'] += 1
            elif amenity == 'atm':
                poi_breakdown['atms'] += 1
            elif amenity == 'bank':
                poi_breakdown['banks'] += 1
            elif shop == 'alcohol':
                poi_breakdown['alcohol_shops'] += 1
        
        # Risk scoring based on POI density
        if poi_count >= 10:
            risk_score = 2  # High Risk: Dense commercial/nightlife area
        elif poi_count >= 3:
            risk_score = 1  # Medium Risk: Moderate activity
        else:
            risk_score = 0  # Low Risk: Quiet area
        
        return risk_score, poi_count, poi_breakdown
        
    except requests.exceptions.RequestException as e:
        print(f"Overpass API error: {e}")
        # Fallback to neutral score if API fails
        return 1, 0, {}
    except Exception as e:
        print(f"Environmental scoring error: {e}")
        return 1, 0, {}


# --- DATABASE DEPENDENCY ---

# --- FASTAPI APP INITIALIZATION ---

app = FastAPI(title="Geospatial Crime Predictor API")

# Initialize CORS Middleware (Crucial fix from earlier!)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
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
        return {"hotspots": [], "count": 0}

    # Format output for the frontend with correct field names
    formatted_hotspots = [
        {
            "latitude": h.latitude,    # Changed from "lat" to "latitude"
            "longitude": h.longitude,  # Changed from "lon" to "longitude"
            "type": h.crime_type
        } 
        for h in hotspots 
        if h.latitude is not None and h.longitude is not None  # Filter out NULL values
    ]
    
    return {"hotspots": formatted_hotspots, "count": len(formatted_hotspots)}


@app.post("/predict_risk")
async def predict_risk(location_data: LocationInput, fast_mode: bool = False, db: Session = Depends(get_db)):
    """
    THREE-LAYER DYNAMIC PREDICTION SYSTEM
    
    Layer 1 (Historical - 20%): ML model trained on 2001-2014 data
    Layer 2 (Environmental - 50%): Real-time OSM POI density analysis  
    Layer 3 (Contextual - 30%): Recent crime news (48-hour window)
    
    This approach bridges the 11-year gap between training data and present day.
    
    fast_mode: If True, skips expensive operations for route analysis
    """
    lat = location_data.latitude
    lon = location_data.longitude
    
    if not crime_model:
        raise HTTPException(status_code=503, detail="ML Model not loaded.")

    # --- LAYER 1: HISTORICAL SCORE (The Past) ---
    current_time = datetime.now()
    day_name = current_time.strftime('%A')
    hour = current_time.hour
    
    h3_index = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)
    h3_boundary = h3.cell_to_boundary(h3_index)

    # REAL XGBoost Prediction
    try:
        # Encode features using the same encoders from training
        # Handle unseen H3 indices gracefully
        try:
            h3_encoded = h3_index_encoder.transform([h3_index])[0]
        except ValueError:
            # H3 index not seen during training - use a default/average encoding
            print(f"Warning: H3 index {h3_index} not in training data. Using fallback.")
            h3_encoded = 0  # Default to first encoding
        
        try:
            day_encoded = day_encoder.transform([day_name])[0]
        except ValueError:
            # Day name issue (shouldn't happen but be safe)
            print(f"Warning: Day {day_name} not in training data. Using fallback.")
            day_encoded = 0
        
        # Create feature vector: [h3_index_encoded, day_encoded, hour_of_day]
        features = [[h3_encoded, day_encoded, hour]]
        
        # Get prediction from XGBoost model (0=Low, 1=Medium, 2=High)
        historical_prediction = crime_model.predict(features)[0]
        historical_score = int(historical_prediction)
        
        print(f"Layer 1 (Historical - XGBoost): {historical_score}/2 for h3={h3_index[:10]}..., day={day_name}, hour={hour}")
    except Exception as e:
        print(f"Warning: XGBoost prediction failed: {e}. Using fallback.")
        # Fallback to medium risk if prediction fails
        historical_score = 1
    
    print(f"Layer 1 (Historical): {historical_score}/2")

    # --- LAYER 2: ENVIRONMENTAL SCORE (The Present-Day World) ---
    # Skip POI lookup in fast mode (expensive API call)
    if fast_mode:
        environmental_score = 1  # Default to medium
        poi_count = 0
        poi_breakdown = {"bars": 0, "nightclubs": 0, "atms": 0, "banks": 0, "alcohol_shops": 0}
    else:
        environmental_score, poi_count, poi_breakdown = get_environmental_risk_score(lat, lon, radius_meters=500)
    
    print(f"Layer 2 (Environmental): {environmental_score}/2 (POIs: {poi_count})")
    
    # --- LAYER 3: CONTEXTUAL SCORE (The Immediate-Term) ---
    # Skip news lookup in fast mode (expensive DB query)
    if fast_mode:
        contextual_score = 1  # Default to medium
        news_count = 0
        news_articles = []
    else:
        context_radius_meters = 1500 
        time_window = datetime.now() - timedelta(hours=24)
        
        context_query = db.query(NewsArticle).filter(
            (NewsArticle.published_at >= time_window) & 
            (
                ST_DWithin(
                    NewsArticle.location,
                    ST_SetSRID(ST_MakePoint(lon, lat), 4326),
                    context_radius_meters
                )
            )
        ).limit(10)
        
        recent_context = context_query.all()
        context_count = len(recent_context)
        
        # Contextual risk scoring
        if context_count >= 3:
            contextual_score = 2  # High: Multiple recent incidents
        elif context_count >= 1:
            contextual_score = 1  # Medium: Some recent activity
        else:
            contextual_score = 0  # Low: No recent news
        
        news_count = context_count
        news_articles = [
            {
                'title': article.title,
                'published_at': article.published_at.isoformat() if article.published_at else None,
                'url': article.url
            } 
            for article in recent_context
        ]
    
    print(f"Layer 3 (Contextual): {contextual_score}/2 (News: {news_count})")
    
    # --- WEIGHTED COMBINATION ---
    final_score_raw = (
        (historical_score * WEIGHT_HISTORICAL) +
        (environmental_score * WEIGHT_ENVIRONMENTAL) +
        (contextual_score * WEIGHT_CONTEXTUAL)
    )
    
    # Convert to 0, 1, 2 risk code
    final_risk_code = round(final_score_raw)
    final_risk_code = max(0, min(2, final_risk_code))  # Clamp to [0, 2]
    
    risk_level = {0: "green", 1: "yellow", 2: "red"}.get(final_risk_code, "yellow")
    
    print(f"\nFinal Score: {final_score_raw:.2f} → Risk Code: {final_risk_code} ({risk_level.upper()})\n")
    
    # --- RESPONSE WITH DETAILED BREAKDOWN ---
    
    # Format contextual news data (only if not in fast mode)
    context_data = news_articles if not fast_mode else []
    
    # Explanation for the user
    explanation_parts = []
    
    if environmental_score == 2:
        explanation_parts.append(f"High-density area ({poi_count} bars/ATMs/nightclubs nearby)")
    elif environmental_score == 1:
        explanation_parts.append(f"Moderate activity area ({poi_count} commercial POIs)")
    else:
        explanation_parts.append("Quiet residential area")
    
    if contextual_score >= 1:
        explanation_parts.append(f"{context_count} crime report(s) in past 48 hours")
    
    if historical_score == 2:
        explanation_parts.append("Historically high-risk location")
    
    explanation = " + ".join(explanation_parts) if explanation_parts else "Standard risk assessment"

    return {
        "risk_level": risk_level,
        "risk_code": final_risk_code,
        "risk_score_raw": round(final_score_raw, 2),
        "explanation": explanation,
        
        # Layer breakdown for transparency
        "layer_scores": {
            "historical": {
                "score": historical_score,
                "weight": WEIGHT_HISTORICAL,
                "contribution": round(historical_score * WEIGHT_HISTORICAL, 2)
            },
            "environmental": {
                "score": environmental_score,
                "weight": WEIGHT_ENVIRONMENTAL,
                "contribution": round(environmental_score * WEIGHT_ENVIRONMENTAL, 2),
                "poi_count": poi_count,
                "poi_breakdown": poi_breakdown
            },
            "contextual": {
                "score": contextual_score,
                "weight": WEIGHT_CONTEXTUAL,
                "contribution": round(contextual_score * WEIGHT_CONTEXTUAL, 2),
                "news_count": context_count,
                "news_articles": context_data
            }
        },
        
        # Map visualization data
        "h3_index": h3_index,
        "h3_boundary": h3_boundary,
        "current_time": current_time.isoformat(),
    }


@app.post("/add_crime")
async def add_crime(secret_key: str, # Security check via environment variable
                db: Session = Depends(get_db)):
    """
    Endpoint 3: Placeholder for adding individual crime reports (currently bypassed by worker).
    """
    # This endpoint is now a placeholder as the worker writes directly to DB.
    expected_key = os.getenv('API_SECRET_KEY')
    if not expected_key or secret_key != expected_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid secret key")
    
    return {"status": "Endpoint is active but worker uses direct DB access for news_corpus."}