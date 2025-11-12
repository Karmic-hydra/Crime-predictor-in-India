Step 1: Clone Repository and Setup Environment

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

Create a file named .env in the root directory to store your credentials securely.

Variable Name

Description

Example Value

DATABASE_URL

Cloud DB Connection String (e.g., Neon URL. Must point to your PostGIS database.)

postgresql://user:pass@host/db

NEWS_API_KEY

Your key for accessing NewsAPI.org.

a1b2c3d4e5f6g7h8i9j0

API_SECRET_KEY

A secret key for the /add_crime endpoint (used by the worker).

my-secure-worker-key

Step 3: Run the Components (3 Terminals Required)

You must run all three parts concurrently for the full system to be operational.

Terminal 1: FastAPI Backend (API Server)

This starts the API that handles data fetching (/get_hotspots) and machine learning predictions (/predict_risk). This is now connected to your cloud PostGIS database.

# Ensure venv is activated
uvicorn main:app --reload --port 8000


Terminal 2: Frontend Dashboard (Browser)

Since the frontend is a single HTML file, you need a local server to serve it. We assume it runs on port 5500.

Use a VS Code extension like Live Server to open index.html.

Alternatively, use Python's built-in server:

python -m http.server 5500


Navigate to http://127.0.0.1:5500/index.html in your browser.

Terminal 3: Live News Worker (Data Ingestion)

This script continuously monitors news sources and inserts new, confirmed crime events into your cloud database.

# Ensure venv and .env variables are loaded
python news_worker.py


🌐 Public Deployment (For Reference)

The architecture is designed for cloud deployment:

API (main.py): Deployed to a service like Render or Heroku.

Scheduler (schedule_training.yml): Runs daily via GitHub Actions to keep the model updated.

Frontend (index.html): Hosted statically via Netlify or Vercel.

Database: Hosted on Neon or Supabase with PostGIS enabled.
