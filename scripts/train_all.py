import sys
import os

# Add root project dir to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.ml.train_xgboost import train_models
from backend.app.ml.train_isolation_forest import train_isolation_forest

if __name__ == "__main__":
    print("========================================")
    print(" Starting AEGIS-Health ML Pipeline Training")
    print("========================================\n")

    print("1. Training Isolation Forest Anomaly Detector...")
    train_isolation_forest()

    print("\n2. Training XGBoost Classifier & Regressor (+ evaluasi held-out, termasuk IF)...")
    train_models()

    print("\n========================================")
    print(" All models trained successfully!")
    print(" Check backend/models_trained/ for outputs.")
    print("========================================")
