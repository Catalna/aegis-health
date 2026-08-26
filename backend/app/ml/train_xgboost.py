"""
Training + evaluation XGBoost (classifier & cost regressor) dengan
HELD-OUT TEST SET yang benar-benar independen (PRD Section 10 anti-tautologi):

- Training set : generate_dataset(seed=101, prefix="TRAIN")
- Held-out set : generate_dataset(seed=202, prefix="HOLD") — panggilan generator
  terpisah dengan seed berbeda, tidak pernah dilihat saat tuning.

Evaluasi dilakukan HANYA di held-out set, termasuk breakdown recall per jenis
anomali (upcoding, cloning, dst.) dan deteksi Isolation Forest.
"""
import json
import os
import numpy as np
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, f1_score, roc_auc_score, average_precision_score

from backend.app.data.synthetic_generator import generate_dataset
from backend.app.ml.feature_engineering import extract_features, FEATURE_NAMES

TRAIN_SEED = 101
HOLDOUT_SEED = 202  # sengaja beda — held-out set independen

# backend/app/ml/ → naik 2 level → backend/models_trained (lokasi yang dibaca financial_engine & API)
MODELS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "models_trained"))


def _vectorize(data):
    X = np.array([extract_features(c) for c in data])
    y = np.array([1 if c["is_synthetic_anomaly"] else 0 for c in data])
    cost = np.array([c["cost_claimed"] for c in data])
    return X, y, cost


def train_models():
    print("=== [1/5] Generating TRAINING dataset (independent seed) ===")
    train_data = generate_dataset(
        num_normal=2000, num_upcoding=150, num_cloning_pairs=50,
        num_repeat_billing=100, num_phantom=100, num_prolonged_los=100,
        num_inflated=100, num_unbundling_groups=50,
        seed=TRAIN_SEED, claim_prefix="TRAIN",
    )
    X_train, yc_train, yr_train = _vectorize(train_data)

    print(f"Training samples: {len(X_train)} | fraud rate: {yc_train.mean():.1%}")

    print("=== [2/5] Generating HELD-OUT test dataset (independent seed) ===")
    holdout_data = generate_dataset(
        num_normal=500, num_upcoding=40, num_cloning_pairs=10,
        num_repeat_billing=25, num_phantom=25, num_prolonged_los=25,
        num_inflated=25, num_unbundling_groups=10,
        seed=HOLDOUT_SEED, claim_prefix="HOLD",
    )
    X_test, yc_test, yr_test = _vectorize(holdout_data)
    print(f"Held-out samples: {len(X_test)} | fraud rate: {yc_test.mean():.1%}")

    # Validation split dari training set (untuk early stopping signal)
    from sklearn.model_selection import train_test_split
    X_tr, X_val, yc_tr, yc_val, yr_tr, yr_val = train_test_split(
        X_train, yc_train, yr_train, test_size=0.15, random_state=42, stratify=yc_train,
    )

    os.makedirs(MODELS_DIR, exist_ok=True)

    print("=== [3/5] Training XGBoost Classifier ===")
    clf = xgb.XGBClassifier(
        objective="binary:logistic",
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        random_state=42,
        eval_metric="aucpr",
    )
    clf.fit(X_tr, yc_tr, eval_set=[(X_val, yc_val)], verbose=False)
    clf.save_model(os.path.join(MODELS_DIR, "xgboost_classifier.json"))

    print("=== [4/5] Training XGBoost Cost Regressor (normal claims only) ===")
    normal_idx = (yc_tr == 0)
    reg = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=200,
        learning_rate=0.05,
        max_depth=4,
        random_state=42,
    )
    reg.fit(X_tr[normal_idx], yr_tr[normal_idx])
    reg.save_model(os.path.join(MODELS_DIR, "xgboost_regressor.json"))

    # Regressor evaluation di held-out normal claims (MAPE)
    normal_test = (yc_test == 0)
    if normal_test.any():
        pred_cost = reg.predict(X_test[normal_test])
        mape = float(np.mean(np.abs((yr_test[normal_test] - pred_cost) / yr_test[normal_test])) * 100)
    else:
        mape = None

    print("=== [5/5] Evaluating on HELD-OUT set ===")
    y_pred_proba = clf.predict_proba(X_test)[:, 1]
    y_pred = clf.predict(X_test)

    xgb_metrics = {
        "precision": float(precision_score(yc_test, y_pred)),
        "recall": float(recall_score(yc_test, y_pred)),
        "f1": float(f1_score(yc_test, y_pred)),
        "roc_auc": float(roc_auc_score(yc_test, y_pred_proba)),
        "pr_auc": float(average_precision_score(yc_test, y_pred_proba)),
    }

    lr = LogisticRegression(max_iter=1000, random_state=42)
    lr.fit(X_tr, yc_tr)
    lr_pred_proba = lr.predict_proba(X_test)[:, 1]
    lr_pred = lr.predict(X_test)
    lr_metrics = {
        "precision": float(precision_score(yc_test, lr_pred)),
        "recall": float(recall_score(yc_test, lr_pred)),
        "f1": float(f1_score(yc_test, lr_pred)),
        "roc_auc": float(roc_auc_score(yc_test, lr_pred_proba)),
        "pr_auc": float(average_precision_score(yc_test, lr_pred_proba)),
    }

    # Recall per jenis anomali (held-out) — bukti deteksi tiap pola fraud
    per_type = {}
    for atype in ("upcoding", "cloning", "repeat_billing", "phantom_billing",
                  "prolonged_los", "inflated_bill", "unbundling"):
        idx = [i for i, c in enumerate(holdout_data)
               if c.get("anomaly_type") == atype or
               (atype == "cloning" and c.get("anomaly_type") == "none" and c["claim_id"].endswith("A") and "-CLN-" in c["claim_id"])]
        if not idx:
            continue
        sub_y = yc_test[idx]
        sub_pred = y_pred[idx]
        per_type[atype] = {
            "count": len(idx),
            "recall": float(recall_score(sub_y, sub_pred, zero_division=0)),
        }

    # Isolation Forest detection rate di held-out (unsupervised baseline)
    if_metrics = {}
    try:
        import joblib
        if_path = os.path.join(MODELS_DIR, "isolation_forest.pkl")
        if os.path.exists(if_path):
            iso = joblib.load(if_path)
            iso_pred = iso.predict(X_test)
            iso_outlier = (iso_pred == -1).astype(int)
            if_metrics = {
                "detection_rate_anomalies": float(np.mean(iso_outlier[yc_test == 1])) if (yc_test == 1).any() else None,
                "false_positive_rate_normal": float(np.mean(iso_outlier[yc_test == 0])) if (yc_test == 0).any() else None,
            }
    except Exception as e:
        print(f"IF evaluation skipped: {e}")

    importance_dict = dict(zip(FEATURE_NAMES, map(float, clf.feature_importances_)))
    sorted_importance = dict(sorted(importance_dict.items(), key=lambda item: item[1], reverse=True))

    eval_results = {
        "methodology": {
            "train_seed": TRAIN_SEED,
            "holdout_seed": HOLDOUT_SEED,
            "note": "Held-out test set digenerate terpisah dengan seed berbeda — tidak dilihat saat tuning (anti-tautologi, PRD Section 10).",
        },
        "dataset": {
            "total_samples": len(X_train) + len(X_test),
            "train_size": len(X_train),
            "val_size": len(X_val),
            "test_size": len(X_test),
            "fraud_rate": float(np.mean(np.concatenate([yc_train, yc_test]))),
        },
        "xgboost_classifier": xgb_metrics,
        "logistic_regression_baseline": lr_metrics,
        "xgboost_regressor": {
            "trained_on": "normal claims (baseline biaya wajar)",
            "mape_pct_normal_holdout": mape,
        },
        "isolation_forest": if_metrics,
        "recall_per_anomaly_type": per_type,
        "feature_importance": sorted_importance,
    }

    with open(os.path.join(MODELS_DIR, "evaluation_results.json"), "w") as f:
        json.dump(eval_results, f, indent=4)

    print("\n=== RESULTS (held-out test) ===")
    print(f"XGBoost  : P={xgb_metrics['precision']:.3f} R={xgb_metrics['recall']:.3f} F1={xgb_metrics['f1']:.3f}")
    print(f"Baseline : P={lr_metrics['precision']:.3f} R={lr_metrics['recall']:.3f} F1={lr_metrics['f1']:.3f}")
    if mape is not None:
        print(f"Regressor MAPE (normal): {mape:.1f}%")
    print("Training complete. Results saved to backend/models_trained/")


if __name__ == "__main__":
    train_models()
