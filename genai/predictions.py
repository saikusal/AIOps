import json
import os
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

try:
    from xgboost import XGBClassifier
except Exception:
    XGBClassifier = None

from .models import PredictionSnapshot, ServicePrediction

MODEL_VERSION = "service-risk-xgb-v1"
FEATURE_COLUMNS = [
    "up",
    "request_rate",
    "latency_p95_seconds",
    "error_rate",
    "dependency_count",
    "dependent_count",
    "blast_radius_size",
    "active_alert_count",
]


def _model_dir() -> str:
    path = os.path.join(os.path.dirname(__file__), "data", "models")
    os.makedirs(path, exist_ok=True)
    return path


def model_path() -> str:
    return os.path.join(_model_dir(), "service_risk_model.joblib")


def metadata_path() -> str:
    return os.path.join(_model_dir(), "service_risk_model_metadata.json")


def build_feature_row(component: Dict[str, Any]) -> Dict[str, float]:
    metrics = component.get("metrics") or {}
    return {
        "up": float(metrics.get("up") or 0.0),
        "request_rate": float(metrics.get("request_rate") or 0.0),
        "latency_p95_seconds": float(metrics.get("latency_p95_seconds") or 0.0),
        "error_rate": float(metrics.get("error_rate") or 0.0),
        "dependency_count": float(len(component.get("depends_on") or [])),
        "dependent_count": float(len((component.get("dependency_context") or {}).get("direct_dependents", []))),
        "blast_radius_size": float(len(component.get("blast_radius") or [])),
        "active_alert_count": float(
            sum(1 for alert in (component.get("recent_alerts") or []) if alert.get("status") == "firing")
        ),
    }


def _heuristic_probability(features: Dict[str, float], status: str) -> float:
    score = 0.05
    score += min(features["latency_p95_seconds"] / 4.0, 0.35)
    score += min(features["error_rate"] * 3.0, 0.35)
    score += min(features["blast_radius_size"] * 0.04, 0.15)
    score += min(features["active_alert_count"] * 0.1, 0.2)
    if features["up"] <= 0:
        score = max(score, 0.98)
    elif status == "degraded":
        score = max(score, 0.65)
    return float(max(0.01, min(score, 0.99)))


def _build_estimator():
    if XGBClassifier is not None:
        return XGBClassifier(
            n_estimators=80,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
        )
    return RandomForestClassifier(n_estimators=160, random_state=42)


def train_model(min_rows: int = 24) -> Dict[str, Any]:
    rows = list(PredictionSnapshot.objects.values("application", "service", "features", "incident_next_15m"))
    if len(rows) < min_rows:
        return {
            "ok": False,
            "detail": f"Not enough labeled snapshots to train. Need at least {min_rows}, found {len(rows)}.",
        }

    frame = pd.DataFrame(
        [
            {**{col: float((row.get("features") or {}).get(col, 0.0)) for col in FEATURE_COLUMNS}, "label": bool(row["incident_next_15m"])}
            for row in rows
        ]
    )
    X = frame[FEATURE_COLUMNS]
    y = frame["label"].astype(int)
    estimator = _build_estimator()
    estimator.fit(X, y)
    joblib.dump(estimator, model_path())
    with open(metadata_path(), "w", encoding="utf-8") as handle:
        json.dump({"model_version": MODEL_VERSION, "feature_columns": FEATURE_COLUMNS}, handle, indent=2)
    return {"ok": True, "detail": f"Trained {MODEL_VERSION} on {len(rows)} snapshots."}


def load_model():
    if not os.path.exists(model_path()):
        return None, {"model_version": "heuristic-v1", "feature_columns": FEATURE_COLUMNS}
    model = joblib.load(model_path())
    metadata = {"model_version": MODEL_VERSION, "feature_columns": FEATURE_COLUMNS}
    if os.path.exists(metadata_path()):
        with open(metadata_path(), "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    return model, metadata


def store_snapshot(component: Dict[str, Any], incident_next_15m: Optional[bool] = None) -> PredictionSnapshot:
    features = build_feature_row(component)
    metrics = component.get("metrics") or {}
    inferred_incident = incident_next_15m
    if inferred_incident is None:
        inferred_incident = component.get("status") in ("degraded", "down") or features["active_alert_count"] > 0
    return PredictionSnapshot.objects.create(
        application=component["application"],
        service=component["service"],
        metrics=metrics,
        features=features,
        incident_next_15m=bool(inferred_incident),
    )


def score_components(components: List[Dict[str, Any]], save_results: bool = True) -> List[Dict[str, Any]]:
    model, metadata = load_model()
    predictions: List[Dict[str, Any]] = []
    for component in components:
        features = build_feature_row(component)
        if model is not None:
            values = pd.DataFrame([{col: features[col] for col in FEATURE_COLUMNS}])[FEATURE_COLUMNS]
            probability = float(model.predict_proba(values)[0][1])
            model_version = metadata.get("model_version", MODEL_VERSION)
        else:
            probability = _heuristic_probability(features, component.get("status", "healthy"))
            model_version = "heuristic-v1"

        if probability >= 0.75:
            risk_status = "high"
        elif probability >= 0.45:
            risk_status = "medium"
        else:
            risk_status = "low"

        explanation = (
            f"Predicted {risk_status} risk for the next 15 minutes based on latency={features['latency_p95_seconds']:.2f}s, "
            f"errors={features['error_rate']:.2f}/s, and blast radius size={int(features['blast_radius_size'])}."
        )
        prediction = {
            "application": component["application"],
            "service": component["service"],
            "risk_score": round(probability, 4),
            "incident_probability": round(probability, 4),
            "predicted_window_minutes": 15,
            "prediction_status": risk_status,
            "model_version": model_version,
            "features": features,
            "explanation": explanation,
            "blast_radius": component.get("blast_radius") or [],
        }
        predictions.append(prediction)
        if save_results:
            ServicePrediction.objects.create(
                application=component["application"],
                service=component["service"],
                status=component.get("status", "healthy"),
                risk_score=probability,
                incident_probability=probability,
                predicted_window_minutes=15,
                model_version=model_version,
                features=features,
                blast_radius=component.get("blast_radius") or [],
                explanation=explanation,
            )
    return predictions
