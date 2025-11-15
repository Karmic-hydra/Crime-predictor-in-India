# 🇮🇳 Crime Risk Predictor for India

> A real-time, AI-powered crime risk assessment system with interactive route analysis and geospatial visualization.

## 🌟 Overview

An intelligent crime prediction platform that combines historical data analysis with environmental and contextual factors to provide accurate risk assessments for any location in India. Features include:

- **Real-time Risk Assessment** - Click anywhere on the map to get instant crime risk predictions
- **Live Route Risk Analysis** - Analyze entire routes with color-coded risk segments (green/yellow/red)
- **Three-Layer Risk System** - Combines historical patterns (XGBoost ML), environmental factors (POI density), and recent news events
- **Interactive Dashboard** - Beautiful, responsive UI with live map visualization
- **Fast Performance** - Optimized with caching and parallel processing for sub-second route analysis

## 💻 Tech Stack

| Category | Technologies | Purpose |
|----------|-------------|---------|
| **Backend** | Python, FastAPI, SQLAlchemy | REST API for predictions and data management |
| **Database** | PostgreSQL, PostGIS, Neon (Cloud) | Geospatial storage with ST_DWithin queries |
| **Machine Learning** | XGBoost, Pandas, Scikit-learn | Crime pattern prediction and classification |
| **Spatial Indexing** | Uber H3 (Resolution 9) | Hexagonal grid for location bucketing (~174m) |
| **Frontend** | HTML5, Tailwind CSS, Leaflet.js | Interactive map with routing capabilities |
| **External APIs** | Overpass API, NewsAPI | POI data and recent crime news |
| **Automation** | GitHub Actions | Daily model retraining at 03:00 UTC |

## 🚀 Quick Start Guide

### Prerequisites

- **Python 3.10+** installed
- **Git** for cloning the repository
- **PostgreSQL with PostGIS** (Cloud database recommended: [Neon](https://neon.tech) or [Supabase](https://supabase.com))
- **NewsAPI Key** (Get free at [newsapi.org](https://newsapi.org))

### Installation

1. **Clone the Repository**
```bash
git clone https://github.com/Karmic-hydra/Crime-predictor-in-India.git
cd Crime-predictor-in-India
```

2. **Set Up Virtual Environment**
```bash
# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure Environment Variables**

Create a `.env` file in the root directory:

```env
# Database Connection (from Neon/Supabase)
DATABASE_URL="postgresql://user:password@host/dbname"

# NewsAPI Key for live data ingestion
NEWS_API_KEY="your-newsapi-key-here"

# API Secret for /add_crime endpoint
API_SECRET_KEY="your-strong-secret-key"
```

5. **Initialize Database**
```bash
python models.py
```

6. **Load Initial Data (Optional)**
```bash
python load_data.py
```

7. **Train the XGBoost Model**
```bash
python train_model.py
```
This creates `crime_model.joblib`, `h3_index_encoder.joblib`, and `day_encoder.joblib` files.

### Running the Application

**Start the Backend Server**
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
Backend will be available at `http://127.0.0.1:8000`

**Open the Frontend**

Simply open `index.html` in your browser, or use a local server:

```bash
# Option 1: Python HTTP Server
python -m http.server 5500

# Option 2: VS Code Live Server Extension
# Right-click index.html → "Open with Live Server"
```

Navigate to `http://127.0.0.1:5500/index.html`

**Start Live News Worker (Optional)**
```bash
python news_worker.py
```
This continuously fetches and processes crime news data.

## 📖 Usage

### Point-Based Risk Assessment
1. Click anywhere on the map
2. View detailed risk breakdown:
   - Historical crime patterns (XGBoost ML prediction)
   - Environmental factors (bars, ATMs, nightclubs nearby)
   - Recent news events (last 48 hours)

### Route Risk Analysis
1. Click **"Analyze My Route"** button
2. Click on the map to set **Start Point** (green marker)
3. Click again to set **End Point** (red marker)
4. Route automatically calculates with color-coded risk:
   - 🟢 **Green** - Low risk (0-33%)
   - 🟡 **Yellow** - Medium risk (34-66%)
   - 🔴 **Red** - High risk (67-100%)
5. Click **"Clear Route"** to reset

### API Endpoints

```bash
# Get risk prediction for a location
POST http://127.0.0.1:8000/predict_risk
{
  "latitude": 12.9716,
  "longitude": 77.5946,
  "fast_mode": false  # true for faster route analysis
}

# Add crime data (requires API_SECRET_KEY)
POST http://127.0.0.1:8000/add_crime
{
  "state": "Karnataka",
  "district": "Bengaluru",
  # ... other fields
}

# API documentation
GET http://127.0.0.1:8000/docs
```


## 🏗️ Architecture

### Three-Layer Risk Scoring System

1. **Historical Layer (20%)** - XGBoost ML model trained on crime patterns
   - Uses H3 spatial indexing (resolution 9 hexagons)
   - Considers location and day of week
   - Graceful fallback for unseen locations

2. **Environmental Layer (50%)** - Real-time POI analysis via Overpass API
   - Queries bars, nightclubs, ATMs, banks within 500m radius
   - Higher density = higher risk score

3. **Contextual Layer (30%)** - Recent news events
   - Searches crime articles within 1500m radius
   - Time window: Last 48 hours
   - Stored in PostGIS-enabled news_corpus table

### Performance Optimizations

- **Frontend Caching** - Map-based cache with 3 decimal precision (~111m resolution)
- **Parallel API Calls** - Promise.all() for simultaneous requests
- **Fast Mode** - Backend skips expensive POI/news queries for route analysis
- **Dynamic Sampling** - Routes limited to max 15 API calls
- **Result**: Sub-second route analysis with caching

## 📁 Project Structure

```
Crime-predictor-in-India/
├── main.py                    # FastAPI backend server
├── models.py                  # SQLAlchemy database models
├── train_model.py             # XGBoost model training script
├── load_data.py               # CSV data loader utility
├── news_worker.py             # News scraping worker
├── index.html                 # Interactive frontend dashboard
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (not in git)
├── .env.example               # Template for environment setup
├── ALL_INDIA_DATA.csv         # Training dataset
├── crime_model.joblib         # Trained XGBoost model
├── h3_index_encoder.joblib    # H3 location encoder
├── day_encoder.joblib         # Day of week encoder
└── RawData/                   # Raw crime datasets
    ├── crime_dataset_india.csv
    └── FINAL_DATA_WITH_GEOLOCATION.csv
```

## 🌐 Deployment

### Backend (Render/Railway)
```bash
# Build Command
pip install -r requirements.txt

# Start Command
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Frontend (Netlify/Vercel)
- Deploy `index.html` as static site
- Update `API_BASE_URL` to production backend URL

### Automated Model Retraining
- GitHub Actions workflow runs daily at 03:00 UTC
- Pulls latest data and retrains XGBoost model
- Commits updated `.joblib` files

## 🔧 Troubleshooting

**Backend won't start:**
- Check DATABASE_URL is correctly formatted
- Ensure PostGIS extension is enabled: `CREATE EXTENSION postgis;`
- Verify all `.joblib` model files exist

**Frontend shows errors:**
- Confirm backend is running on port 8000
- Check browser console for CORS issues
- Verify `API_BASE_URL` in index.html matches backend

**Slow route analysis:**
- Enable caching (already implemented)
- Use fast_mode for route requests
- Check network connection to Overpass API

**Model training fails:**
- Ensure `ALL_INDIA_DATA.csv` exists and has correct format
- Check for missing dependencies: `pip install xgboost scikit-learn`
- Verify sufficient memory (model requires ~500MB RAM)

## 📊 Dataset

Training data from official Indian government crime statistics (ALL_INDIA_DATA.csv):
- **Records**: 50,000+ crime incidents across India
- **Features**: State, District, Crime Type, Geolocation (lat/lon), Date/Time
- **Coverage**: Multiple years of historical data
- **H3 Resolution**: Level 9 (~174m hexagons)

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## 👨‍💻 Author

**Karmic-hydra**
- GitHub: [@Karmic-hydra](https://github.com/Karmic-hydra)
- Repository: [Crime-predictor-in-India](https://github.com/Karmic-hydra/Crime-predictor-in-India)

## 🙏 Acknowledgments

- Indian Government for crime statistics data
- Uber H3 for hexagonal spatial indexing
- OpenStreetMap & Overpass API for POI data
- Leaflet.js for mapping capabilities
- XGBoost team for ML framework

---

⭐ **Star this repo if you find it useful!**
