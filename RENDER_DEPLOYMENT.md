# Render Deployment Guide

## Quick Start

1. **Push your code to GitHub** (models will be trained automatically on Render)

2. **Create a new Web Service on Render:**
   - Connect your GitHub repository
   - Use these settings:

## Render Configuration

### Build Settings
- **Build Command:** `./build.sh`
- **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Environment Variables
Add these in Render dashboard:

```
DATABASE_URL=<your-postgresql-connection-string>
API_SECRET_KEY=<your-secret-key>
NEWSAPI_KEY=<your-newsapi-key>
```

### Important Notes

1. **First deployment will take 5-10 minutes** because models need to be trained
2. Models are trained automatically from `ALL_INDIA_DATA.csv` 
3. Subsequent deployments will be faster (models are cached)
4. Make sure `ALL_INDIA_DATA.csv` is committed to your repository

## Alternative: Pre-commit Models with Git LFS

If you prefer to commit model files (faster deployments):

```bash
# Install Git LFS
git lfs install

# Track joblib files
git lfs track "*.joblib"

# Add and commit
git add .gitattributes
git add *.joblib
git commit -m "Add ML models with Git LFS"
git push
```

Then remove `./build.sh` from Build Command and use:
```
pip install -r requirements.txt
```

## Troubleshooting

### Models not loading
- Check Render logs for training output
- Ensure `ALL_INDIA_DATA.csv` exists in repo
- Verify build script has execution permissions

### Database connection issues
- Confirm DATABASE_URL is set correctly
- Check PostgreSQL with PostGIS extension is enabled
- Verify network access from Render to database

### Port binding errors
- Render sets PORT automatically - use `$PORT` in start command
- Don't hardcode port 8000 in production
