"""
Pydantic v2 data schemas for request/response validation.
Covers sensor data, prediction I/O, feedback, health, model quality,
CSV upload, simulation, multi-machine monitoring, and alerts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INPUT SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SensorData(BaseModel):
    """Validated sensor readings from the machine."""

    temperature_celsius: float = Field(
        default=25.0, ge=-50.0, le=500.0,
        description="Machine surface / bearing temperature in °C",
    )
    vibration_mms: float = Field(
        default=0.5, ge=0.0, le=100.0,
        description="Vibration amplitude in mm/s RMS",
    )
    pressure_bar: float = Field(
        default=5.0, ge=0.0, le=500.0,
        description="Hydraulic / pneumatic pressure in bar",
    )
    rpm: float = Field(
        default=1500.0, ge=0.0, le=50000.0,
        description="Rotational speed in RPM",
    )
    load_percent: float = Field(
        default=50.0, ge=0.0, le=150.0,
        description="Mechanical load as percentage of rated capacity",
    )
    voltage_v: float = Field(
        default=230.0, ge=0.0, le=10000.0,
        description="Supply voltage in volts",
    )
    current_a: float = Field(
        default=10.0, ge=0.0, le=5000.0,
        description="Motor current draw in amperes",
    )
    operating_hours: float = Field(
        default=1000.0, ge=0.0, le=500000.0,
        description="Cumulative machine operating hours",
    )


class PredictionRequest(BaseModel):
    """Single-machine prediction request."""

    machine_id: str = Field(
        ..., min_length=1, max_length=128,
        description="Unique identifier of the machine",
    )
    tenant_id: str = Field(
        ..., min_length=1, max_length=64,
        description="Tenant / plant identifier for multi-tenant isolation",
    )
    machine_type: str = Field(
        default="general",
        description="Type of machine (e.g. pump, compressor, conveyor)",
    )
    criticality: str = Field(
        default="medium",
        description="Criticality level: low, medium, high, critical",
    )
    last_maintenance_days: int = Field(
        default=30, ge=0, le=3650,
        description="Days since last maintenance",
    )
    machine_age_months: int = Field(
        default=24, ge=0, le=1200,
        description="Machine age in months",
    )
    sensors: SensorData = Field(
        default_factory=SensorData,
        description="Current sensor readings",
    )

    @field_validator("criticality")
    @classmethod
    def validate_criticality(cls, v: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        v_lower = v.lower().strip()
        if v_lower not in allowed:
            raise ValueError(f"criticality must be one of {allowed}")
        return v_lower


class BatchPredictionRequest(BaseModel):
    """Batch wrapper — up to 50 machines per request."""

    requests: List[PredictionRequest] = Field(
        ..., min_length=1, max_length=50,
        description="List of individual prediction requests",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OUTPUT SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AnomalyAlert(BaseModel):
    """A single anomaly detection alert for a sensor."""
    sensor: str
    display_name: str
    value: float
    unit: str
    normal_range: str
    severity: str  # "warning" or "critical"
    message: str


class PredictionResponse(BaseModel):
    """Prediction result for a single machine."""

    prediction_id: str = Field(description="Unique prediction identifier")
    machine_id: str
    tenant_id: str
    model_version: str
    model_trained_at: str
    timestamp: datetime

    # ── Core output fields ───────────────────────────────────────────────
    failure_risk_percentage: float = Field(
        ge=0.0, le=100.0,
        description="Overall failure probability 0-100%",
    )
    failure_probability: float = Field(
        ge=0.0, le=1.0,
        description="Failure probability as 0-1 decimal",
    )
    failure_primary_cause: str = Field(
        description="Most likely failure mode (e.g. bearing_wear)",
    )
    failure_type: str = Field(
        description="ML model classified failure type",
    )
    confidence_score: float = Field(
        ge=0.0, le=100.0,
        description="ML model confidence in the prediction (0-100%)",
    )
    remaining_useful_life: float = Field(
        ge=0.0,
        description="Estimated remaining useful life in operational hours",
    )
    maintenance_recommendation: str = Field(
        description="Human-readable maintenance advice",
    )

    # ── Health & Risk ────────────────────────────────────────────────────
    health_score: int = Field(
        ge=0, le=100,
        description="Machine health score 0-100 (higher = healthier)",
    )
    health_status: str = Field(
        description="Human-readable health status: Healthy/Fair/Warning/Poor/Critical",
    )
    risk_level: str = Field(
        default="medium",
        description="Categorised risk: low / medium / high / critical",
    )

    # ── Anomaly Detection ────────────────────────────────────────────────
    anomalies: List[AnomalyAlert] = Field(
        default_factory=list,
        description="List of detected sensor anomalies",
    )

    # ── AI Explainability ────────────────────────────────────────────────
    feature_importance: Dict[str, float] = Field(
        default_factory=dict,
        description="Per-sensor contribution to the risk score (from trained RF model)",
    )
    class_probabilities: Dict[str, float] = Field(
        default_factory=dict,
        description="Probability of each failure class from the ML model",
    )


class BatchPredictionResponse(BaseModel):
    """Wrapper for batch predictions."""

    predictions: List[PredictionResponse]
    total: int
    processing_time_ms: float


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CSV UPLOAD SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class CSVUploadResponse(BaseModel):
    """Response from CSV data upload and prediction."""
    filename: str
    rows_processed: int
    predictions: List[PredictionResponse]
    processing_time_ms: float


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MULTI-MACHINE MONITORING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class MachineStatus(BaseModel):
    """Status summary of a single machine for multi-machine view."""
    machine_id: str
    machine_type: str
    health_score: int
    health_status: str
    risk_level: str
    failure_risk_percentage: float
    failure_primary_cause: str
    remaining_useful_life: float
    anomaly_count: int
    last_updated: datetime


class FactoryDashboardResponse(BaseModel):
    """Factory-wide dashboard summary."""
    total_machines: int
    healthy_count: int
    warning_count: int
    critical_count: int
    machines: List[MachineStatus]
    avg_health_score: float
    timestamp: datetime


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ALERT SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AlertItem(BaseModel):
    """A single alert item."""
    alert_id: str
    machine_id: str
    sensor: str
    severity: str
    message: str
    value: float
    threshold: str
    timestamp: datetime


class AlertsResponse(BaseModel):
    """Collection of active alerts."""
    total: int
    alerts: List[AlertItem]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FEEDBACK SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class FeedbackRequest(BaseModel):
    """Operator feedback on a previous prediction."""

    prediction_id: str = Field(
        ..., min_length=1, max_length=128,
        description="The prediction_id returned by /predict_failure",
    )
    machine_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str = Field(..., min_length=1, max_length=64)
    actual_failure_occurred: bool = Field(
        description="Did the predicted failure actually happen?",
    )
    actual_failure_cause: Optional[str] = Field(
        default=None,
        description="Real root cause observed (if failure occurred)",
    )
    actual_rul_hours: Optional[float] = Field(
        default=None, ge=0,
        description="Observed remaining useful life at time of prediction",
    )
    operator_notes: Optional[str] = Field(
        default=None, max_length=2000,
        description="Free-text operator notes",
    )


class FeedbackResponse(BaseModel):
    """Acknowledgement of feedback submission."""

    feedback_id: str
    status: str = "recorded"
    message: str = "Feedback stored successfully"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OPERATIONAL SCHEMAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class HealthResponse(BaseModel):
    """Service health check response."""

    status: str = "healthy"
    service: str
    version: str
    model_version: str
    uptime_seconds: float
    timestamp: datetime


class ModelQualityResponse(BaseModel):
    """Aggregated model quality metrics derived from operator feedback."""

    total_feedback: int
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    mean_rul_error_hours: Optional[float] = None
    drift_detected: bool = False
    drift_message: Optional[str] = None
    feedback_by_tenant: Dict[str, int] = Field(default_factory=dict)
    last_updated: datetime


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DEMO MODE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class DemoResponse(BaseModel):
    """Response for demo mode start/stop."""
    status: str
    message: str
