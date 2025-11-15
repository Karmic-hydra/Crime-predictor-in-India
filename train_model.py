import pandas as pd
import joblib
import h3
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report
import os

# --- 1. LOAD DATA FROM CSV FILE ---
print("--- 1. Loading data from ALL_INDIA_DATA.csv... ---")

csv_file = "ALL_INDIA_DATA.csv"

if not os.path.exists(csv_file):
    print(f"--- ERROR: {csv_file} not found! ---")
    exit()

try:
    df = pd.read_csv(csv_file)
    print(f"Successfully loaded {len(df)} records from {csv_file}.")
    print(f"Columns: {df.columns.tolist()}")
except Exception as e:
    print(f"--- ERROR: Could not load data from CSV. --- \nError: {e}")
    exit()

# --- 2. FEATURE ENGINEERING (THE H3 GRID) ---
print("--- 2. Starting Feature Engineering with H3... ---")
H3_RESOLUTION = 9

# Check if latitude and longitude columns exist
required_cols = ['latitude', 'longitude']
if not all(col in df.columns for col in required_cols):
    print(f"--- ERROR: CSV must have columns: {required_cols} ---")
    print(f"Found columns: {df.columns.tolist()}")
    exit()

# Handle potential missing/invalid coordinates
df = df.dropna(subset=['latitude', 'longitude'])
df = df[(df['latitude'] >= -90) & (df['latitude'] <= 90)]
df = df[(df['longitude'] >= -180) & (df['longitude'] <= 180)]

print(f"After cleaning coordinates: {len(df)} records remaining.")
print(f"Using h3.latlng_to_cell() at resolution {H3_RESOLUTION}...")

df['h3_index'] = df.apply(
    lambda row: h3.latlng_to_cell(row['latitude'], row['longitude'], H3_RESOLUTION),
    axis=1
)

print("Aggregating data into (H3 Index, Day, Hour) slots...")

# Check if 'days' and 'hour_of_day' columns exist, create if needed
if 'days' not in df.columns and 'Day' in df.columns:
    df['days'] = df['Day']
if 'hour_of_day' not in df.columns and 'Hour' in df.columns:
    df['hour_of_day'] = df['Hour']
if 'count' not in df.columns:
    # If no count column, assume each row is 1 incident
    df['count'] = 1

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

# --- 7. TRAIN THE MODEL WITH XGBOOST ---
print("--- 5. Training the XGBoost model... ---")
X_train, X_test, y_train, y_test = train_test_split(
    X_features, y, test_size=0.2, random_state=42, stratify=y
)

# XGBoost Classifier with optimized parameters
model = xgb.XGBClassifier(
    n_estimators=200,           # More trees for better accuracy
    max_depth=8,                # Deeper trees than RF default
    learning_rate=0.1,          # Standard learning rate
    subsample=0.8,              # Use 80% of data per tree
    colsample_bytree=0.8,       # Use 80% of features per tree
    objective='multi:softmax',  # Multi-class classification
    num_class=3,                # 3 risk levels (Low/Medium/High)
    random_state=42,
    n_jobs=-1,                  # Use all CPU cores
    eval_metric='mlogloss'      # Multi-class log loss
)

print("Training in progress (this may take a few minutes)...")
model.fit(X_train, y_train)

# --- 8. EVALUATE AND SAVE ---
print("--- 6. Model training complete. Evaluating... ---")
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_pred)
print(f"\n{'='*60}")
print(f"🎯 XGBoost Model Accuracy: {accuracy:.4f} ({accuracy*100:.2f}%)")
print(f"{'='*60}")
print("\n📊 Classification Report:")
print(classification_report(y_test, y_pred, target_names=['Low (0)', 'Medium (1)', 'High (2)']))

# Feature importance
feature_importance = model.feature_importances_
feature_names = ['H3 Location', 'Day of Week', 'Hour of Day']
print("\n🔍 Feature Importance:")
for name, importance in zip(feature_names, feature_importance):
    print(f"  {name}: {importance:.4f}")

print("\n--- 7. Saving XGBoost model and encoders... ---")
joblib.dump(model, 'crime_model.joblib')
joblib.dump(h3_encoder, 'h3_index_encoder.joblib')
joblib.dump(day_encoder, 'day_encoder.joblib')

print("\n✅ SUCCESS! XGBoost Model Training Complete.")
print("📦 Saved files:")
print("  - crime_model.joblib (XGBoost model)")
print("  - h3_index_encoder.joblib")
print("  - day_encoder.joblib")
print("\n🚀 Your XGBoost model is ready for the API!")