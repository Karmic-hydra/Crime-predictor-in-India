import pandas as pd
import joblib
import h3
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sqlalchemy import create_engine
from models import DATABASE_URL  # Import your DB URL from models.py

# --- 1. LOAD DATA FROM DATABASE ---
print("--- 1. Loading data from PostGIS database... ---")

engine = create_engine(DATABASE_URL)
sql_query = "SELECT latitude, longitude, days, hour_of_day, count FROM crimes;"

try:
    df = pd.read_sql(sql_query, engine)
    print(f"Successfully loaded {len(df)} records from the database.")
except Exception as e:
    print(f"--- ERROR: Could not load data from database. --- \nError: {e}")
    exit()

# --- 2. FEATURE ENGINEERING (THE H3 GRID) ---
print("--- 2. Starting Feature Engineering with H3... ---")
H3_RESOLUTION = 9
print(f"Using h3.latlng_to_cell() at resolution {H3_RESOLUTION}...")
df['h3_index'] = df.apply(
    lambda row: h3.latlng_to_cell(row['latitude'], row['longitude'], H3_RESOLUTION),
    axis=1
)

print("Aggregating data into (H3 Index, Day, Hour) slots...")
df_grouped = df.groupby(['h3_index', 'days', 'hour_of_day'])['count'].sum().reset_index()
df_grouped = df_grouped.rename(columns={'count': 'crime_count'})

# --- 3. CREATE "ZERO" SAMPLES ---
print("Creating 'zero-crime' samples...")
unique_h3 = df_grouped['h3_index'].unique()
unique_days = df_grouped['days'].unique()
unique_hours = df_grouped['hour_of_day'].unique()

all_slots = pd.MultiIndex.from_product(
    [unique_h3, unique_days, unique_hours],
    names=['h3_index', 'days', 'hour_of_day']
).to_frame(index=False)

df_final = pd.merge(all_slots, df_grouped, on=['h3_index', 'days', 'hour_of_day'], how='left')
df_final['crime_count'] = df_final['crime_count'].fillna(0)

# --- 4. DEFINE TARGET VARIABLE (Risk Levels) ---
print("Defining risk levels...")
def define_risk(count):
    if count > 5:  # You can adjust this threshold
        return 2  # 2 = High (Red)
    elif count > 0:
        return 1  # 1 = Medium (Yellow)
    else:
        return 0  # 0 = Low (Green)
df_final['risk_level'] = df_final['crime_count'].apply(define_risk)

# --- 5. !!! NEW FIX: DOWNSAMPLING TO PREVENT MEMORY ERROR !!! ---
print("--- 3. Downsampling 'Low' risk data to balance dataset... ---")

# Separate the 'crime' (Medium/High) from 'no_crime' (Low)
df_crime = df_final[df_final['risk_level'] > 0]
df_no_crime = df_final[df_final['risk_level'] == 0]

print(f"Found {len(df_crime)} 'Medium/High' risk samples.")
print(f"Found {len(df_no_crime)} 'Low' risk samples (too many).")

# We will sample the 'Low' data to be equal to the 'Medium/High' data
# This creates a balanced 50/50 dataset and saves memory
df_no_crime_sampled = df_no_crime.sample(n=len(df_crime), random_state=42)

print(f"Taking 100% of 'Medium/High' samples and {len(df_no_crime_sampled)} 'Low' samples.")

# Combine them back into a final, balanced DataFrame
df_balanced = pd.concat([df_crime, df_no_crime_sampled])

print(f"New balanced dataset size: {len(df_balanced)} rows (manageable).")
# --- END OF FIX ---


# --- 6. ENCODING & MODEL PREPARATION ---
print("--- 4. Preparing data for model... ---")

# We now use the 'df_balanced' DataFrame
X = df_balanced[['h3_index', 'days', 'hour_of_day']]
y = df_balanced['risk_level']

h3_encoder = LabelEncoder()
day_encoder = LabelEncoder()

# --- FIX for SettingWithCopyWarning ---
# Use .loc to assign the new columns safely
X.loc[:, 'h3_index_encoded'] = h3_encoder.fit_transform(X['h3_index'])
X.loc[:, 'day_encoded'] = day_encoder.fit_transform(X['days'])
# --- END OF FIX ---

X_features = X[['h3_index_encoded', 'day_encoded', 'hour_of_day']]

# --- 7. TRAIN THE MODEL ---
print("--- 5. Training the RandomForest model... ---")
X_train, X_test, y_train, y_test = train_test_split(
    X_features, y, test_size=0.2, random_state=42, stratify=y
)

# We use n_jobs=1 to prevent memory spikes. It's safer.
model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=1)
model.fit(X_train, y_train)

# --- 8. EVALUATE AND SAVE ---
print("--- 6. Model training complete. Evaluating... ---")
y_pred = model.predict(X_test)

print(f"Model Accuracy: {accuracy_score(y_test, y_pred):.4f}")
print("\nClassification Report:")
print(classification_report(y_test, y_pred, target_names=['Low (0)', 'Medium (1)', 'High (2)']))

print("--- 7. Saving model and encoders... ---")
joblib.dump(model, 'crime_model.joblib')
joblib.dump(h3_encoder, 'h3_index_encoder.joblib')
joblib.dump(day_encoder, 'day_encoder.joblib')

print("\n--- SUCCESS! Phase 3 Complete. ---")
print("Your models are saved and ready for the API.")