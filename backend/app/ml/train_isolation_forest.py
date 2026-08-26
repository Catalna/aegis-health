import os
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from backend.app.data.synthetic_generator import generate_dataset
from backend.app.ml.feature_engineering import extract_features

def train_isolation_forest():
    print("Generating pure NORMAL dataset for Isolation Forest...")
    # Unsupervised models should ideally be trained on "clean" data to learn what is normal
    data = generate_dataset(
        num_normal=1500,
        num_upcoding=0,
        num_cloning_pairs=0,
        num_repeat_billing=0,
        num_phantom=0,
        num_prolonged_los=0,
        num_inflated=0,
        num_unbundling_groups=0,
        seed=303,  # seed berbeda dari training XGBoost (101) & held-out (202)
        claim_prefix="IF",
    )
    
    X_train = []
    for claim in data:
        X_train.append(extract_features(claim))
        
    X_train = np.array(X_train)
    
    os.makedirs("backend/models_trained", exist_ok=True)
    
    print("Training Isolation Forest...")
    iso_forest = IsolationForest(
        n_estimators=200, 
        max_samples='auto', 
        contamination=0.01, # Assume 1% of our "normal" data might be noisy
        max_features=1.0, 
        random_state=42
    )
    
    iso_forest.fit(X_train)
    
    # Save model via joblib (since scikit-learn doesn't have native save_model like XGBoost)
    joblib.dump(iso_forest, "backend/models_trained/isolation_forest.pkl")
    print("Isolation Forest trained and saved to backend/models_trained/isolation_forest.pkl")

if __name__ == "__main__":
    train_isolation_forest()
