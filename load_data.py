import pandas as pd
from models import SessionLocal, Crime, engine # Import from models.py
from sqlalchemy.orm import sessionmaker
import os
import importlib

# --- 1. CONFIGURATION ---
CSV_FILE_PATH = "ALL_INDIA_DATA.csv" 

# --- 2. LOAD CSV ---
try:
    df = pd.read_csv(CSV_FILE_PATH)
    print(f"Loaded {len(df)} rows from {CSV_FILE_PATH}")
except FileNotFoundError:
    print("--- ERROR: File Not Found ---")
    print(f"Could not find file at: {CSV_FILE_PATH}")
    exit()

# --- 3. PREPARE DATA FOR BULK INSERT ---
df = df.dropna(subset=['latitude', 'longitude'])
print(f"Total rows to insert after cleaning: {len(df)}")

# --- !!! THIS IS THE FIX !!! ---
# Convert NumPy types (np.int64) to standard Python types (int, float)
print("Converting data types...")
df['year'] = df['year'].astype(int)
df['count'] = df['count'].astype(float)
df['hour_of_day'] = df['hour_of_day'].astype(int)
df['minute'] = df['minute'].astype(int)
df['latitude'] = df['latitude'].astype(float)
df['longitude'] = df['longitude'].astype(float)
# String columns are fine as-is
# --- !!! END OF FIX !!! ---

print("Converting data to dictionary...")
data_dict = df.to_dict(orient='records')

print("Preparing PostGIS geometry...")
for row in data_dict:
    # SRID=4326 must match your models.py
    row['location'] = f'SRID=4326;POINT({row["longitude"]} {row["latitude"]})'

# --- 4. CONNECT AND BULK INSERT ---
Session = sessionmaker(bind=engine)
session = Session()

print("Starting bulk insert. This may take a minute...")

try:
    # Drop and recreate the crimes table
    models = importlib.import_module('models')
    models.Base.metadata.drop_all(bind=models.engine, tables=[models.Crime.__table__])
    models.Base.metadata.create_all(bind=models.engine, tables=[models.Crime.__table__])
    print('Dropped and recreated crimes table')
    
    session.bulk_insert_mappings(Crime, data_dict)
    session.commit()
    
    print("\n--- SUCCESS! ---")
    print(f"All {len(data_dict)} rows have been loaded into the database.")

except Exception as e:
    print(f"\n--- ERROR ---")
    print(f"An error occurred: {e}")
    session.rollback()

finally:
    session.close() 
    print("Session closed.")