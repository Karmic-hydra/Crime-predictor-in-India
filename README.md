🇮🇳 End-to-End Geospatial Crime Predictor

Project Title

End-to-End Geospatial Crime Predictor

🌟 Overview and Goal

This project is a high-availability, full-stack web application that provides real-time crime risk assessment and visualization of historical crime data for all of India, with an emphasis on fine-grained prediction for Bengaluru.

The architecture combines a powerful geospatial database (PostGIS) with a machine learning model (RandomForest) trained on the Uber H3 grid system, ensuring highly accurate, location- and time-specific risk predictions.

💻 Tech Stack Highlights

Category

Core Technologies

Key Function

Backend API

Python, FastAPI, SQLAlchemy

Serves prediction and hotspot data.

Database

PostgreSQL, PostGIS, Neon/Supabase (Cloud)

Geospatial storage and querying (ST_DWithin).

Data Science

Pandas, Scikit-learn (RandomForest), H3

Model training and location indexing.

Frontend

HTML, Tailwind CSS, Leaflet.js

Interactive map visualization (Heatmaps, H3 Polygons).

Live Updates

NewsAPI, Hugging Face NER, GitHub Actions

Continuous data ingestion and daily model retraining.

🚀 Local Setup and Execution

To run the full application locally, you must run three separate processes concurrently, all connecting to your remote PostGIS database.

Prerequisites

Python 3.10+

git

psql command-line tool (for database setup)

A Cloud PostGIS Database (e.g., Neon)

NewsAPI Key (For the Live Worker)

Step 1: Clone and Install Dependencies

# Clone the repository
git clone [https://github.com/Karmic-hydra/Crime-predictor-in-India.git](https://github.com/Karmic-hydra/Crime-predictor-in-India.git)
cd Crime-predictor-in-India

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate # On Windows
source venv/bin/activate # On Linux/macOS

# Install dependencies
pip install -r requirements.txt


Step 2: Configure Environment Variables

Create a file named .env in the root directory to securely store your credentials.

# Cloud Database URL (from Neon/Supabase - without the ?options= search_path parameter)
DATABASE_URL="postgresql://[user]:[password]@[host]/[dbname]"

# Key required for news data ingestion
NEWS_API_KEY="your-newsapi-key-here"

# Secret used to secure the /add_crime endpoint
API_SECRET_KEY="your-strong-worker-secret"


Step 3: Run All Three Services

Open three separate terminal windows (or tabs), activate the venv in each, and run the following commands:

Terminal 1: Start FastAPI Backend (API Server)

# Runs on [http://127.0.0.1:8000](http://127.0.0.1:8000)
uvicorn main:app --reload --port 8000


Terminal 2: Serve Frontend Dashboard

This serves the index.html file, which accesses the API running on port 8000.

# Runs on [http://127.0.0.1:5500](http://127.0.0.1:5500) (assuming VS Code Live Server or similar)
python -m http.server 5500


Then navigate to http://127.0.0.1:5500/index.html in your web browser.

Terminal 3: Start Live News Worker

This worker runs indefinitely, fetching, processing, and submitting new crime data to your cloud database.

python news_worker.py


🌐 Deployment Architecture

The entire system is containerized and separated for reliability:

Component

Deployment Service

Purpose

FastAPI Backend

Render / Google App Engine

Publicly accessible API endpoint.

Frontend Dashboard

Netlify / Vercel (Static Host)

Serves the static index.html.

Model Retraining

GitHub Actions (Cron Job)

Runs train_model.py daily at 03:00 AM UTC.

Live Worker

DigitalOcean Droplet / Cloud Function

Runs 24/7 for data ingestion.

License

This project is licensed under the MIT License.
