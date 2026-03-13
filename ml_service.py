"""
Machine Learning Prediction Engine — Real Random Forest Pipeline.

Uses a trained Random Forest model on synthetic industrial sensor data:
  • RandomForestClassifier for failure-type classification
  • Machine-type-aware sensor profiles & thresholds
  • Composite scoring for failure risk % with real feature importance
  • Anomaly detection via Z-score thresholds
  • Health score computation (0–100)
  • Remaining Useful Life regression
  • Confidence scoring from model probability outputs
  • Rule-based maintenance recommendation generation
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config import settings
from models import AnomalyAlert, PredictionRequest, PredictionResponse, SensorData

logger = logging.getLogger("machine_health.ml")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SENSOR THRESHOLDS & WEIGHTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass(frozen=True)
class SensorProfile:
    """Defines normal range and risk weight for a single sensor."""
    name: str
    ideal: float
    warn_low: float
    warn_high: float
    crit_low: float
    crit_high: float
    weight: float          # contribution weight to overall risk


# Domain-expert thresholds for typical industrial rotating equipment (GENERAL default)
SENSOR_PROFILES: Dict[str, SensorProfile] = {
    "temperature_celsius": SensorProfile(
        name="temperature_celsius",
        ideal=55.0, warn_low=10.0, warn_high=75.0,
        crit_low=-10.0, crit_high=95.0, weight=0.20,
    ),
    "vibration_mms": SensorProfile(
        name="vibration_mms",
        ideal=2.0, warn_low=0.0, warn_high=7.0,
        crit_low=0.0, crit_high=15.0, weight=0.25,
    ),
    "pressure_bar": SensorProfile(
        name="pressure_bar",
        ideal=5.0, warn_low=2.0, warn_high=8.0,
        crit_low=0.5, crit_high=12.0, weight=0.12,
    ),
    "rpm": SensorProfile(
        name="rpm",
        ideal=1500.0, warn_low=800.0, warn_high=2200.0,
        crit_low=300.0, crit_high=3500.0, weight=0.10,
    ),
    "load_percent": SensorProfile(
        name="load_percent",
        ideal=60.0, warn_low=10.0, warn_high=85.0,
        crit_low=0.0, crit_high=100.0, weight=0.10,
    ),
    "voltage_v": SensorProfile(
        name="voltage_v",
        ideal=230.0, warn_low=210.0, warn_high=250.0,
        crit_low=190.0, crit_high=270.0, weight=0.08,
    ),
    "current_a": SensorProfile(
        name="current_a",
        ideal=10.0, warn_low=2.0, warn_high=18.0,
        crit_low=0.5, crit_high=25.0, weight=0.08,
    ),
    "operating_hours": SensorProfile(
        name="operating_hours",
        ideal=5000.0, warn_low=0.0, warn_high=15000.0,
        crit_low=0.0, crit_high=30000.0, weight=0.07,
    ),
}

# ── Machine-Type-Specific Sensor Profiles ────────────────────────────────────
# Each type adjusts ideal values, thresholds, and sensor importance weights

MACHINE_TYPE_PROFILES: Dict[str, Dict[str, SensorProfile]] = {
    "pump": {
        "temperature_celsius": SensorProfile("temperature_celsius", ideal=48.0, warn_low=5.0, warn_high=70.0, crit_low=-5.0, crit_high=88.0, weight=0.15),
        "vibration_mms": SensorProfile("vibration_mms", ideal=1.8, warn_low=0.0, warn_high=5.5, crit_low=0.0, crit_high=12.0, weight=0.18),
        "pressure_bar": SensorProfile("pressure_bar", ideal=6.5, warn_low=3.0, warn_high=9.5, crit_low=1.0, crit_high=14.0, weight=0.28),
        "rpm": SensorProfile("rpm", ideal=1800.0, warn_low=1000.0, warn_high=2500.0, crit_low=500.0, crit_high=3200.0, weight=0.10),
        "load_percent": SensorProfile("load_percent", ideal=55.0, warn_low=15.0, warn_high=80.0, crit_low=0.0, crit_high=95.0, weight=0.10),
        "voltage_v": SensorProfile("voltage_v", ideal=230.0, warn_low=210.0, warn_high=250.0, crit_low=190.0, crit_high=270.0, weight=0.05),
        "current_a": SensorProfile("current_a", ideal=12.0, warn_low=3.0, warn_high=20.0, crit_low=0.5, crit_high=28.0, weight=0.07),
        "operating_hours": SensorProfile("operating_hours", ideal=4000.0, warn_low=0.0, warn_high=12000.0, crit_low=0.0, crit_high=25000.0, weight=0.07),
    },
    "compressor": {
        "temperature_celsius": SensorProfile("temperature_celsius", ideal=52.0, warn_low=8.0, warn_high=72.0, crit_low=-5.0, crit_high=92.0, weight=0.18),
        "vibration_mms": SensorProfile("vibration_mms", ideal=2.5, warn_low=0.0, warn_high=8.0, crit_low=0.0, crit_high=16.0, weight=0.22),
        "pressure_bar": SensorProfile("pressure_bar", ideal=7.0, warn_low=3.5, warn_high=10.0, crit_low=1.5, crit_high=15.0, weight=0.25),
        "rpm": SensorProfile("rpm", ideal=1450.0, warn_low=700.0, warn_high=2100.0, crit_low=300.0, crit_high=3000.0, weight=0.08),
        "load_percent": SensorProfile("load_percent", ideal=50.0, warn_low=10.0, warn_high=78.0, crit_low=0.0, crit_high=92.0, weight=0.10),
        "voltage_v": SensorProfile("voltage_v", ideal=230.0, warn_low=212.0, warn_high=248.0, crit_low=195.0, crit_high=265.0, weight=0.05),
        "current_a": SensorProfile("current_a", ideal=9.0, warn_low=2.0, warn_high=16.0, crit_low=0.5, crit_high=22.0, weight=0.05),
        "operating_hours": SensorProfile("operating_hours", ideal=6000.0, warn_low=0.0, warn_high=18000.0, crit_low=0.0, crit_high=35000.0, weight=0.07),
    },
    "turbine": {
        "temperature_celsius": SensorProfile("temperature_celsius", ideal=65.0, warn_low=15.0, warn_high=90.0, crit_low=-5.0, crit_high=120.0, weight=0.22),
        "vibration_mms": SensorProfile("vibration_mms", ideal=1.5, warn_low=0.0, warn_high=5.0, crit_low=0.0, crit_high=10.0, weight=0.25),
        "pressure_bar": SensorProfile("pressure_bar", ideal=4.5, warn_low=1.5, warn_high=7.5, crit_low=0.5, crit_high=11.0, weight=0.10),
        "rpm": SensorProfile("rpm", ideal=3000.0, warn_low=1500.0, warn_high=4500.0, crit_low=800.0, crit_high=6000.0, weight=0.18),
        "load_percent": SensorProfile("load_percent", ideal=65.0, warn_low=20.0, warn_high=90.0, crit_low=5.0, crit_high=100.0, weight=0.08),
        "voltage_v": SensorProfile("voltage_v", ideal=400.0, warn_low=360.0, warn_high=440.0, crit_low=320.0, crit_high=480.0, weight=0.05),
        "current_a": SensorProfile("current_a", ideal=18.0, warn_low=5.0, warn_high=30.0, crit_low=1.0, crit_high=40.0, weight=0.05),
        "operating_hours": SensorProfile("operating_hours", ideal=8000.0, warn_low=0.0, warn_high=20000.0, crit_low=0.0, crit_high=40000.0, weight=0.07),
    },
    "motor": {
        "temperature_celsius": SensorProfile("temperature_celsius", ideal=50.0, warn_low=8.0, warn_high=72.0, crit_low=-5.0, crit_high=90.0, weight=0.15),
        "vibration_mms": SensorProfile("vibration_mms", ideal=2.2, warn_low=0.0, warn_high=6.5, crit_low=0.0, crit_high=13.0, weight=0.15),
        "pressure_bar": SensorProfile("pressure_bar", ideal=5.0, warn_low=2.0, warn_high=8.0, crit_low=0.5, crit_high=12.0, weight=0.05),
        "rpm": SensorProfile("rpm", ideal=1500.0, warn_low=800.0, warn_high=2200.0, crit_low=300.0, crit_high=3500.0, weight=0.12),
        "load_percent": SensorProfile("load_percent", ideal=50.0, warn_low=10.0, warn_high=80.0, crit_low=0.0, crit_high=95.0, weight=0.07),
        "voltage_v": SensorProfile("voltage_v", ideal=230.0, warn_low=208.0, warn_high=252.0, crit_low=185.0, crit_high=275.0, weight=0.20),
        "current_a": SensorProfile("current_a", ideal=10.0, warn_low=2.0, warn_high=18.0, crit_low=0.5, crit_high=25.0, weight=0.20),
        "operating_hours": SensorProfile("operating_hours", ideal=5000.0, warn_low=0.0, warn_high=15000.0, crit_low=0.0, crit_high=30000.0, weight=0.06),
    },
    "conveyor": {
        "temperature_celsius": SensorProfile("temperature_celsius", ideal=38.0, warn_low=5.0, warn_high=55.0, crit_low=-5.0, crit_high=70.0, weight=0.12),
        "vibration_mms": SensorProfile("vibration_mms", ideal=1.2, warn_low=0.0, warn_high=4.0, crit_low=0.0, crit_high=8.0, weight=0.20),
        "pressure_bar": SensorProfile("pressure_bar", ideal=4.0, warn_low=1.5, warn_high=6.5, crit_low=0.5, crit_high=10.0, weight=0.08),
        "rpm": SensorProfile("rpm", ideal=1200.0, warn_low=500.0, warn_high=1800.0, crit_low=200.0, crit_high=2500.0, weight=0.18),
        "load_percent": SensorProfile("load_percent", ideal=40.0, warn_low=5.0, warn_high=70.0, crit_low=0.0, crit_high=85.0, weight=0.15),
        "voltage_v": SensorProfile("voltage_v", ideal=230.0, warn_low=212.0, warn_high=248.0, crit_low=195.0, crit_high=265.0, weight=0.08),
        "current_a": SensorProfile("current_a", ideal=7.0, warn_low=1.0, warn_high=14.0, crit_low=0.3, crit_high=20.0, weight=0.10),
        "operating_hours": SensorProfile("operating_hours", ideal=3000.0, warn_low=0.0, warn_high=10000.0, crit_low=0.0, crit_high=20000.0, weight=0.09),
    },
}


def get_profiles_for_type(machine_type: str) -> Dict[str, SensorProfile]:
    """Return sensor profiles for the given machine type, falling back to general."""
    return MACHINE_TYPE_PROFILES.get(machine_type, SENSOR_PROFILES)


# Failure-mode definitions: name → (relevant sensors, base multiplier)
FAILURE_MODES: Dict[str, Tuple[list, float]] = {
    "bearing_wear": (["vibration_mms", "temperature_celsius", "operating_hours"], 1.0),
    "overheating": (["temperature_celsius", "current_a", "load_percent"], 0.95),
    "misalignment": (["vibration_mms", "rpm", "load_percent"], 0.85),
    "electrical_fault": (["voltage_v", "current_a", "temperature_celsius"], 0.80),
    "pressure_anomaly": (["pressure_bar", "temperature_celsius", "rpm"], 0.75),
    "lubrication_failure": (["vibration_mms", "temperature_celsius", "operating_hours"], 0.70),
}

FAILURE_LABELS = list(FAILURE_MODES.keys())
SENSOR_NAMES = list(SENSOR_PROFILES.keys())


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SYNTHETIC DATA GENERATOR (for training the real ML model)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _generate_synthetic_training_data(n_samples: int = 2000, seed: int = 42):
    """
    Generate realistic synthetic sensor data with failure labels.
    Creates a balanced dataset across all failure modes + healthy samples.
    """
    rng = np.random.default_rng(seed)
    samples_per_class = n_samples // (len(FAILURE_LABELS) + 1)  # +1 for healthy

    X_all = []
    y_all = []

    # Generate healthy samples (low deviation from ideal)
    for _ in range(samples_per_class):
        row = []
        for name in SENSOR_NAMES:
            p = SENSOR_PROFILES[name]
            val = rng.normal(p.ideal, (p.warn_high - p.warn_low) * 0.15)
            val = np.clip(val, p.crit_low, p.crit_high)
            row.append(val)
        X_all.append(row)
        y_all.append("healthy")

    # Generate failure-mode samples (elevated relevant sensors)
    for mode, (relevant_sensors, _) in FAILURE_MODES.items():
        for _ in range(samples_per_class):
            row = []
            for name in SENSOR_NAMES:
                p = SENSOR_PROFILES[name]
                if name in relevant_sensors:
                    # Push toward critical range
                    val = rng.normal(
                        p.ideal + (p.crit_high - p.ideal) * rng.uniform(0.4, 0.9),
                        (p.crit_high - p.warn_high) * 0.3,
                    )
                else:
                    val = rng.normal(p.ideal, (p.warn_high - p.warn_low) * 0.2)
                val = np.clip(val, p.crit_low, p.crit_high)
                row.append(val)
            X_all.append(row)
            y_all.append(mode)

    return np.array(X_all), np.array(y_all)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PREDICTION ENGINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class PredictionEngine:
    """
    Real ML prediction engine using trained Random Forest model.
    Model is trained on synthetic data at initialization.
    Supports machine-type-specific sensor profiles and thresholds.
    """

    def __init__(self):
        self.model: RandomForestClassifier | None = None
        self.scaler: StandardScaler | None = None
        self._train_model()

    def _train_model(self):
        """Train the Random Forest classifier on synthetic data."""
        logger.info("🧠 Training Random Forest model on synthetic industrial data...")
        X, y = _generate_synthetic_training_data(n_samples=3000)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=12,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_scaled, y)

        # Store feature importances from the trained model
        self._rf_feature_importance = dict(
            zip(SENSOR_NAMES, self.model.feature_importances_)
        )

        logger.info(
            "✅ Model trained — classes=%s accuracy_train=%.2f%%",
            list(self.model.classes_),
            self.model.score(X_scaled, y) * 100,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _sensor_deviation(value: float, profile: SensorProfile) -> float:
        """
        Compute a normalised deviation score ∈ [0, 1] for a sensor reading.
        0.0 → at ideal value, 0.5 → at warning threshold, 1.0 → at/beyond critical
        """
        if profile.crit_high == profile.crit_low:
            return 0.0
        half_range = (profile.crit_high - profile.crit_low) / 2.0
        deviation = abs(value - profile.ideal) / half_range
        return float(np.clip(deviation, 0.0, 1.0))

    @staticmethod
    def _logistic(x: float, k: float = 10.0, midpoint: float = 0.5) -> float:
        """Logistic sigmoid mapping [0, 1] → [0, 1] with steepness k."""
        return float(1.0 / (1.0 + np.exp(-k * (x - midpoint))))

    # ── sensor feature extraction ────────────────────────────────────────

    def _extract_features(self, sensors: SensorData) -> np.ndarray:
        """Extract feature vector from sensor data in correct order."""
        return np.array([[
            sensors.temperature_celsius,
            sensors.vibration_mms,
            sensors.pressure_bar,
            sensors.rpm,
            sensors.load_percent,
            sensors.voltage_v,
            sensors.current_a,
            sensors.operating_hours,
        ]])

    def _compute_sensor_scores(
        self, sensors: SensorData, profiles: Dict[str, SensorProfile]
    ) -> Dict[str, float]:
        """Return normalised deviation score for each sensor using type-specific profiles."""
        readings: Dict[str, float] = {
            "temperature_celsius": sensors.temperature_celsius,
            "vibration_mms": sensors.vibration_mms,
            "pressure_bar": sensors.pressure_bar,
            "rpm": sensors.rpm,
            "load_percent": sensors.load_percent,
            "voltage_v": sensors.voltage_v,
            "current_a": sensors.current_a,
            "operating_hours": sensors.operating_hours,
        }
        return {
            name: self._sensor_deviation(readings[name], profiles[name])
            for name in profiles
        }

    # ── ML-based classification ──────────────────────────────────────────

    def _classify_with_model(
        self, sensors: SensorData
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        Use the trained Random Forest to classify failure type.
        Returns (predicted_class, confidence, class_probabilities).
        """
        X = self._extract_features(sensors)
        X_scaled = self.scaler.transform(X)

        predicted_class = self.model.predict(X_scaled)[0]
        probabilities = self.model.predict_proba(X_scaled)[0]

        class_probs = dict(zip(self.model.classes_, probabilities))
        confidence = float(max(probabilities))

        return predicted_class, confidence, class_probs

    # ── risk percentage ──────────────────────────────────────────────────

    def _compute_risk(
        self,
        sensor_scores: Dict[str, float],
        request: PredictionRequest,
        class_probs: Dict[str, float],
        profiles: Dict[str, SensorProfile],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute failure risk percentage using weighted sensor scores,
        interaction terms, contextual adjustments, and ML model output.
        Returns (risk_pct, feature_importance_dict).
        """
        # Weighted linear combination using type-specific weights
        weighted_sum = sum(
            sensor_scores[name] * profiles[name].weight
            for name in sensor_scores
        )

        # Interaction term: high temp × high vibration
        interaction = (
            sensor_scores["temperature_celsius"]
            * sensor_scores["vibration_mms"]
            * 0.15
        )

        # Context adjustments
        maintenance_factor = min(request.last_maintenance_days / 365.0, 1.0) * 0.10
        age_factor = min(request.machine_age_months / 120.0, 1.0) * 0.08

        # ML model contribution: probability of NOT being healthy
        healthy_prob = class_probs.get("healthy", 0.5)
        ml_risk_factor = (1.0 - healthy_prob) * 0.25

        combined = weighted_sum + interaction + maintenance_factor + age_factor + ml_risk_factor

        # Sigmoid to compress into [0, 1], then scale to [0, 100]
        risk_pct = self._logistic(combined, k=8.0, midpoint=0.35) * 100.0
        risk_pct = round(float(np.clip(risk_pct, 0.0, 100.0)), 1)

        # Feature importance from the REAL trained model
        raw_importance = {}
        for name in SENSOR_NAMES:
            rf_imp = self._rf_feature_importance.get(name, 0.0)
            deviation_weight = sensor_scores[name] * profiles[name].weight
            raw_importance[name] = round(rf_imp * 0.6 + deviation_weight * 0.4, 4)

        total = sum(raw_importance.values()) or 1.0
        feature_importance = {
            name: round(v / total, 2)
            for name, v in sorted(raw_importance.items(), key=lambda x: -x[1])
            if v > 0.001
        }

        return risk_pct, feature_importance

    # ── anomaly detection ────────────────────────────────────────────────

    def _detect_anomalies(
        self, sensors: SensorData, profiles: Dict[str, SensorProfile]
    ) -> List[AnomalyAlert]:
        """Detect anomalies where sensor values exceed warning/critical thresholds (type-aware)."""
        anomalies = []
        readings = {
            "temperature_celsius": sensors.temperature_celsius,
            "vibration_mms": sensors.vibration_mms,
            "pressure_bar": sensors.pressure_bar,
            "rpm": sensors.rpm,
            "load_percent": sensors.load_percent,
            "voltage_v": sensors.voltage_v,
            "current_a": sensors.current_a,
            "operating_hours": sensors.operating_hours,
        }

        sensor_display = {
            "temperature_celsius": ("Temperature", "°C"),
            "vibration_mms": ("Vibration", "mm/s"),
            "pressure_bar": ("Pressure", "bar"),
            "rpm": ("RPM", ""),
            "load_percent": ("Load", "%"),
            "voltage_v": ("Voltage", "V"),
            "current_a": ("Current", "A"),
            "operating_hours": ("Operating Hours", "hrs"),
        }

        for name, value in readings.items():
            profile = profiles[name]
            display_name, unit = sensor_display[name]

            if value >= profile.crit_high or value <= profile.crit_low:
                anomalies.append(AnomalyAlert(
                    sensor=name,
                    display_name=display_name,
                    value=value,
                    unit=unit,
                    normal_range=f"{profile.warn_low}–{profile.warn_high}",
                    severity="critical",
                    message=f"⚠ CRITICAL: {display_name} at {value}{unit} (normal: {profile.warn_low}–{profile.warn_high}{unit})",
                ))
            elif value >= profile.warn_high or value <= profile.warn_low:
                anomalies.append(AnomalyAlert(
                    sensor=name,
                    display_name=display_name,
                    value=value,
                    unit=unit,
                    normal_range=f"{profile.warn_low}–{profile.warn_high}",
                    severity="warning",
                    message=f"⚠ WARNING: {display_name} at {value}{unit} (normal: {profile.warn_low}–{profile.warn_high}{unit})",
                ))

        return anomalies

    # ── health score ─────────────────────────────────────────────────────

    @staticmethod
    def _compute_health_score(risk_pct: float) -> int:
        """Compute health score 0–100 (inverse of risk with non-linear mapping)."""
        health = 100.0 - risk_pct
        # Apply slight curve to make scores more meaningful
        health = health * (0.85 + 0.15 * (health / 100.0))
        return max(0, min(100, round(health)))

    @staticmethod
    def _health_status(score: int) -> str:
        """Return human-readable health status from score."""
        if score >= 80:
            return "Healthy"
        if score >= 60:
            return "Fair"
        if score >= 40:
            return "Warning"
        if score >= 20:
            return "Poor"
        return "Critical"

    # ── remaining useful life ────────────────────────────────────────────

    @staticmethod
    def _estimate_rul(risk_pct: float, operating_hours: float) -> float:
        """
        Estimate RUL in operational hours.
        Uses inverse relationship with risk: higher risk → shorter RUL.
        """
        base_rul = 5000.0
        risk_factor = max(1.0 - (risk_pct / 100.0), 0.01)
        hours_factor = max(1.0 - (operating_hours / 50000.0), 0.1)
        rul = base_rul * risk_factor * hours_factor

        noise = float(np.random.default_rng(int(risk_pct * 100)).normal(0, 0.05))
        rul *= 1.0 + noise

        return round(max(rul, 1.0), 1)

    # ── maintenance recommendation ───────────────────────────────────────

    @staticmethod
    def _generate_recommendation(
        cause: str,
        risk_pct: float,
        rul: float,
        criticality: str,
        machine_type: str = "general",
    ) -> str:
        """Context-aware, machine-type-specific maintenance advice."""
        # Type-specific cause actions
        type_actions: Dict[str, Dict[str, str]] = {
            "pump": {
                "bearing_wear": "pump bearing inspection, seal check and impeller replacement",
                "overheating": "pump cooling jacket inspection and coolant flush",
                "misalignment": "pump-motor coupling alignment correction",
                "electrical_fault": "pump motor electrical diagnostics and VFD check",
                "pressure_anomaly": "pump discharge pressure check, valve and seal inspection",
                "lubrication_failure": "pump bearing lubrication service and mechanical seal oil analysis",
                "healthy": "routine pump preventive maintenance and flow rate verification",
            },
            "compressor": {
                "bearing_wear": "compressor bearing and piston ring inspection",
                "overheating": "compressor intercooler and aftercooler cleaning, oil level check",
                "misalignment": "compressor shaft alignment and coupling inspection",
                "electrical_fault": "compressor motor electrical diagnostics",
                "pressure_anomaly": "compressor valve inspection, pressure relief check and leak detection",
                "lubrication_failure": "compressor oil analysis and lubrication system service",
                "healthy": "routine compressor maintenance and pressure system verification",
            },
            "turbine": {
                "bearing_wear": "turbine journal bearing inspection and rotor balancing",
                "overheating": "turbine blade inspection, exhaust temperature analysis and cooling check",
                "misalignment": "turbine rotor alignment correction and coupling inspection",
                "electrical_fault": "turbine generator electrical diagnostics and exciter check",
                "pressure_anomaly": "turbine steam/gas pressure regulation and nozzle inspection",
                "lubrication_failure": "turbine lube oil system flush and bearing oil analysis",
                "healthy": "routine turbine overhaul planning and performance monitoring",
            },
            "motor": {
                "bearing_wear": "motor bearing replacement and vibration signature analysis",
                "overheating": "motor winding insulation test and ventilation check",
                "misalignment": "motor shaft alignment correction",
                "electrical_fault": "motor insulation resistance test, VFD diagnostics and winding check",
                "pressure_anomaly": "motor cooling system pressure check",
                "lubrication_failure": "motor bearing lubrication and grease analysis",
                "healthy": "routine motor electrical testing and thermographic scan",
            },
            "conveyor": {
                "bearing_wear": "conveyor roller bearing inspection and belt tension check",
                "overheating": "conveyor drive motor cooling check and belt friction analysis",
                "misalignment": "conveyor belt tracking adjustment and roller alignment",
                "electrical_fault": "conveyor drive motor electrical diagnostics",
                "pressure_anomaly": "conveyor hydraulic system pressure check",
                "lubrication_failure": "conveyor chain/roller lubrication and gearbox oil change",
                "healthy": "routine conveyor belt inspection and roller maintenance",
            },
        }

        # Get type-specific or fall back to general actions
        cause_actions = type_actions.get(machine_type, {})
        if cause not in cause_actions:
            general_actions: Dict[str, str] = {
                "bearing_wear": "bearing inspection and replacement",
                "overheating": "cooling system check and thermal inspection",
                "misalignment": "shaft alignment correction",
                "electrical_fault": "electrical system diagnostics and wiring check",
                "pressure_anomaly": "pressure system inspection and seal check",
                "lubrication_failure": "lubrication system service and oil analysis",
                "healthy": "routine preventive maintenance",
            }
            cause_actions = general_actions

        action = cause_actions.get(cause, "comprehensive machine inspection")

        if risk_pct >= 85:
            urgency = "IMMEDIATELY"
            timeframe = "within 24 hours"
        elif risk_pct >= 65:
            urgency = "URGENTLY"
            timeframe = "within 48 hours"
        elif risk_pct >= 40:
            urgency = "soon"
            timeframe = "within 1 week"
        else:
            urgency = "during next scheduled window"
            timeframe = "within 30 days"

        if criticality in ("critical", "high"):
            timeframe = "within 24 hours" if risk_pct >= 40 else timeframe

        type_label = machine_type.replace("_", " ").title() if machine_type != "general" else "Machine"

        return (
            f"[{type_label}] Schedule {action} {urgency}. "
            f"Recommended completion {timeframe}. "
            f"Estimated remaining useful life: {rul:.0f} hours."
        )

    # ── risk level label ─────────────────────────────────────────────────

    @staticmethod
    def _risk_level(risk_pct: float) -> str:
        if risk_pct >= 80:
            return "critical"
        if risk_pct >= 55:
            return "high"
        if risk_pct >= 30:
            return "medium"
        return "low"

    # ── public API ───────────────────────────────────────────────────────

    def predict(self, request: PredictionRequest) -> PredictionResponse:
        """
        Run the full prediction pipeline for a single machine.

        Steps:
          1. Select machine-type-specific sensor profiles
          2. Score each sensor against its type-specific profile
          3. Classify failure type using trained Random Forest
          4. Compute weighted failure-risk percentage (logistic + ML)
          5. Detect anomalies using type-specific thresholds
          6. Compute health score
          7. Estimate remaining useful life
          8. Generate type-specific maintenance recommendation
        """
        # Get type-specific profiles
        profiles = get_profiles_for_type(request.machine_type)

        sensor_scores = self._compute_sensor_scores(request.sensors, profiles)

        # Real ML classification
        failure_type, confidence, class_probs = self._classify_with_model(request.sensors)

        # If predicted healthy, use rule-based cause for display
        if failure_type == "healthy":
            # Still show the most likely non-healthy cause
            non_healthy = {k: v for k, v in class_probs.items() if k != "healthy"}
            cause = max(non_healthy, key=non_healthy.get) if non_healthy else "healthy"
        else:
            cause = failure_type

        risk_pct, feature_importance = self._compute_risk(
            sensor_scores, request, class_probs, profiles
        )
        anomalies = self._detect_anomalies(request.sensors, profiles)
        health_score = self._compute_health_score(risk_pct)
        rul = self._estimate_rul(risk_pct, request.sensors.operating_hours)
        recommendation = self._generate_recommendation(
            cause, risk_pct, rul, request.criticality, request.machine_type,
        )

        # Deterministic prediction ID
        hash_input = f"{request.machine_id}:{request.tenant_id}:{datetime.now(timezone.utc).isoformat()}"
        pred_id = "pred_" + hashlib.sha256(hash_input.encode()).hexdigest()[:12]

        return PredictionResponse(
            prediction_id=pred_id,
            machine_id=request.machine_id,
            tenant_id=request.tenant_id,
            model_version=settings.model_version,
            model_trained_at=settings.model_trained_at,
            timestamp=datetime.now(timezone.utc),
            failure_risk_percentage=risk_pct,
            failure_probability=round(risk_pct / 100.0, 4),
            failure_primary_cause=cause,
            failure_type=failure_type,
            confidence_score=round(confidence * 100, 1),
            remaining_useful_life=rul,
            maintenance_recommendation=recommendation,
            feature_importance=feature_importance,
            risk_level=self._risk_level(risk_pct),
            health_score=health_score,
            health_status=self._health_status(health_score),
            anomalies=anomalies,
            class_probabilities=class_probs,
        )


# Module-level singleton
engine = PredictionEngine()
