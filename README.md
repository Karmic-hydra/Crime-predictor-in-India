# Crime Predictor (India)

This repository contains a small project that predicts and visualizes crime risk for locations in India. It includes:

- A FastAPI backend (predictive endpoints)
- A PostGIS-backed PostgreSQL database for historical crime records
- A frontend dashboard using Leaflet/H3 for map visualization (`index.html`)
# Crime Predictor (India)

Minimal quickstart and notes.

Prerequisites
- Python 3.10+
- PostgreSQL with PostGIS

Quick start
1. Create + activate venv:
```powershell
python -m venv venv
& .\venv\Scripts\Activate.ps1
```
2. Install deps:
```powershell
pip install -r requirements.txt
```
3. Edit `models.py` and set `DATABASE_URL`.
4. Enable PostGIS (psql):
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```
5. Create tables and load data:
```powershell
python -c "import importlib; m = importlib.import_module('models'); m.create_tables()"
python create_csv.py
```

Troubleshooting
- If you see `column "state" of relation "crimes" does not exist`, either ALTER the table to add missing columns or DROP & recreate the `crimes` table before loading.

Dependencies
Install with:
```powershell
pip install -r requirements.txt
```

