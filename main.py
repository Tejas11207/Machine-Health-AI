"""
Machine Health Failure Prediction Service — FastAPI Application.

Production-ready REST API for real-time predictive maintenance with:
  • Sensor-based failure-risk prediction (real Random Forest model)
  • Batch processing for multiple machines
  • CSV data upload for industrial sensor data
  • Real-time sensor simulation via WebSocket
  • Multi-machine factory floor monitoring
  • Demo mode for hackathon presentations
  • Anomaly detection and alert system
  • Closed-loop learning via operator feedback
  • Model quality monitoring
  • API key authentication, rate limiting, and CORS
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Dict, List

import numpy as np
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from auth import require_api_key
from config import settings
from feedback import feedback_store
from middleware import LoggingAndLatencyMiddleware, RateLimiterMiddleware
from ml_service import engine
from models import (
    AlertItem,
    AlertsResponse,
    BatchPredictionRequest,
    BatchPredictionResponse,
    CSVUploadResponse,
    DemoResponse,
    FactoryDashboardResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    MachineStatus,
    ModelQualityResponse,
    PredictionRequest,
    PredictionResponse,
    SensorData,
)

# ── Logging setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("machine_health")

# ── Track uptime ─────────────────────────────────────────────────────────────

_start_time: float = time.time()

# ── In-memory state for multi-machine monitoring & demo ──────────────────────

_machine_store: Dict[str, PredictionResponse] = {}
_alerts_store: List[AlertItem] = []
_demo_active: bool = False
_demo_task: asyncio.Task | None = None
_simulation_connections: List[WebSocket] = []


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown lifecycle."""
    logger.info(
        "🚀  %s %s starting  model=%s",
        settings.app_name,
        settings.app_version,
        settings.model_version,
    )
    yield
    global _demo_active, _demo_task
    _demo_active = False
    if _demo_task and not _demo_task.done():
        _demo_task.cancel()
    logger.info("🛑  %s shutting down", settings.app_name)


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Production-grade REST API for industrial machine health monitoring "
        "and predictive maintenance. Accepts real-time sensor data and returns "
        "failure-risk predictions, root-cause classification, remaining useful "
        "life estimates, and maintenance recommendations."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Middleware (order matters: outermost runs first) ─────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(LoggingAndLatencyMiddleware)

# ── Static files ─────────────────────────────────────────────────────────────

_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ROUTES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# ── Health check (public) ────────────────────────────────────────────────────


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Operations"],
    summary="Service health check",
)
async def health_check() -> HealthResponse:
    """
    Returns service health status, version information, and uptime.
    Used by load balancers and monitoring systems — no auth required.
    """
    return HealthResponse(
        status="healthy",
        service=settings.app_name,
        version=settings.app_version,
        model_version=settings.model_version,
        uptime_seconds=round(time.time() - _start_time, 2),
        timestamp=datetime.now(timezone.utc),
    )


# ── Single prediction ───────────────────────────────────────────────────────


@app.post(
    "/predict_failure",
    response_model=PredictionResponse,
    tags=["Predictions"],
    summary="Predict failure risk for a single machine",
    status_code=status.HTTP_200_OK,
)
async def predict_failure(
    request: PredictionRequest,
    api_key: str = Depends(require_api_key),
) -> PredictionResponse:
    """
    Accept sensor readings and machine context for **one machine** and return:
    - **failure_risk_percentage** — 0-100 float
    - **failure_probability** — 0-1 decimal
    - **failure_primary_cause** — e.g. `bearing_wear`, `overheating`
    - **failure_type** — ML model classified type
    - **confidence_score** — ML model confidence %
    - **remaining_useful_life** — hours
    - **health_score** — 0-100 machine health
    - **anomalies** — list of detected sensor anomalies
    - **maintenance_recommendation** — human-readable advice
    - **feature_importance** — from trained Random Forest model
    """
    try:
        prediction = engine.predict(request)
        # Store in machine monitor
        _machine_store[request.machine_id] = prediction
        # Generate alerts from anomalies
        _process_alerts(request.machine_id, prediction)

        logger.info(
            "Prediction  machine=%s  tenant=%s  risk=%.1f%%  cause=%s  health=%d  confidence=%.1f%%",
            request.machine_id,
            request.tenant_id,
            prediction.failure_risk_percentage,
            prediction.failure_primary_cause,
            prediction.health_score,
            prediction.confidence_score,
        )
        return prediction
    except Exception as exc:
        logger.exception("Prediction failed for machine=%s", request.machine_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction engine error: {exc}",
        ) from exc


# ── Batch prediction ────────────────────────────────────────────────────────


@app.post(
    "/predict_batch",
    response_model=BatchPredictionResponse,
    tags=["Predictions"],
    summary="Batch-predict failure risk for multiple machines",
    status_code=status.HTTP_200_OK,
)
async def predict_batch(
    batch: BatchPredictionRequest,
    api_key: str = Depends(require_api_key),
) -> BatchPredictionResponse:
    """Process up to **50 machines** in a single request."""
    start = time.perf_counter()
    predictions: list[PredictionResponse] = []

    for req in batch.requests:
        try:
            pred = engine.predict(req)
            predictions.append(pred)
            _machine_store[req.machine_id] = pred
            _process_alerts(req.machine_id, pred)
        except Exception as exc:
            logger.error("Batch item failed  machine=%s: %s", req.machine_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Prediction failed for machine {req.machine_id}: {exc}",
            ) from exc

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info("Batch prediction  count=%d  latency=%.2fms", len(predictions), elapsed_ms)

    return BatchPredictionResponse(
        predictions=predictions,
        total=len(predictions),
        processing_time_ms=round(elapsed_ms, 2),
    )


# ── CSV Upload ──────────────────────────────────────────────────────────────


@app.post(
    "/upload_csv",
    response_model=CSVUploadResponse,
    tags=["Data Upload"],
    summary="Upload sensor data CSV for batch prediction",
    status_code=status.HTTP_200_OK,
)
async def upload_csv(
    file: UploadFile = File(...),
    api_key: str = Depends(require_api_key),
) -> CSVUploadResponse:
    """
    Upload a CSV file with sensor data columns:
    temperature, vibration, pressure, rpm, load, voltage, current, operating_hours

    Each row is processed as a separate machine prediction.
    """
    start = time.perf_counter()

    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted",
        )

    content = await file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))

    predictions = []
    row_num = 0

    # Map possible CSV column names to our sensor fields
    column_map = {
        "temperature": "temperature_celsius",
        "temperature_celsius": "temperature_celsius",
        "temp": "temperature_celsius",
        "vibration": "vibration_mms",
        "vibration_mms": "vibration_mms",
        "vib": "vibration_mms",
        "pressure": "pressure_bar",
        "pressure_bar": "pressure_bar",
        "rpm": "rpm",
        "load": "load_percent",
        "load_percent": "load_percent",
        "voltage": "voltage_v",
        "voltage_v": "voltage_v",
        "current": "current_a",
        "current_a": "current_a",
        "operating_hours": "operating_hours",
        "hours": "operating_hours",
    }

    for row in reader:
        row_num += 1
        sensor_data = {}
        for csv_col, value in row.items():
            mapped = column_map.get(csv_col.strip().lower())
            if mapped:
                try:
                    sensor_data[mapped] = float(value.strip())
                except (ValueError, AttributeError):
                    pass

        machine_id = row.get("machine_id", f"CSV-{row_num:03d}")
        tenant_id = row.get("tenant_id", "csv_upload")

        request = PredictionRequest(
            machine_id=machine_id,
            tenant_id=tenant_id,
            sensors=SensorData(**sensor_data),
        )

        pred = engine.predict(request)
        predictions.append(pred)
        _machine_store[machine_id] = pred
        _process_alerts(machine_id, pred)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info("CSV upload  file=%s  rows=%d  latency=%.2fms", file.filename, row_num, elapsed_ms)

    return CSVUploadResponse(
        filename=file.filename or "unknown.csv",
        rows_processed=row_num,
        predictions=predictions,
        processing_time_ms=round(elapsed_ms, 2),
    )


# ── Multi-Machine Factory Dashboard ─────────────────────────────────────────


@app.get(
    "/machines",
    response_model=FactoryDashboardResponse,
    tags=["Monitoring"],
    summary="Get all monitored machines status",
)
async def get_machines(
    api_key: str = Depends(require_api_key),
) -> FactoryDashboardResponse:
    """Return factory floor dashboard with status of all monitored machines."""
    machines = []
    for mid, pred in _machine_store.items():
        machines.append(MachineStatus(
            machine_id=pred.machine_id,
            machine_type="general",
            health_score=pred.health_score,
            health_status=pred.health_status,
            risk_level=pred.risk_level,
            failure_risk_percentage=pred.failure_risk_percentage,
            failure_primary_cause=pred.failure_primary_cause,
            remaining_useful_life=pred.remaining_useful_life,
            anomaly_count=len(pred.anomalies),
            last_updated=pred.timestamp,
        ))

    healthy = sum(1 for m in machines if m.risk_level == "low")
    warning = sum(1 for m in machines if m.risk_level in ("medium", "high"))
    critical = sum(1 for m in machines if m.risk_level == "critical")
    avg_health = sum(m.health_score for m in machines) / max(len(machines), 1)

    return FactoryDashboardResponse(
        total_machines=len(machines),
        healthy_count=healthy,
        warning_count=warning,
        critical_count=critical,
        machines=machines,
        avg_health_score=round(avg_health, 1),
        timestamp=datetime.now(timezone.utc),
    )


# ── Alerts ───────────────────────────────────────────────────────────────────


def _process_alerts(machine_id: str, prediction: PredictionResponse):
    """Generate alerts from prediction anomalies."""
    global _alerts_store
    for anomaly in prediction.anomalies:
        alert = AlertItem(
            alert_id=f"alert_{uuid.uuid4().hex[:8]}",
            machine_id=machine_id,
            sensor=anomaly.sensor,
            severity=anomaly.severity,
            message=anomaly.message,
            value=anomaly.value,
            threshold=anomaly.normal_range,
            timestamp=datetime.now(timezone.utc),
        )
        _alerts_store.append(alert)

    # Keep only last 100 alerts
    if len(_alerts_store) > 100:
        _alerts_store = _alerts_store[-100:]


@app.get(
    "/alerts",
    response_model=AlertsResponse,
    tags=["Monitoring"],
    summary="Get active alerts",
)
async def get_alerts(
    api_key: str = Depends(require_api_key),
) -> AlertsResponse:
    """Return all active sensor threshold alerts."""
    return AlertsResponse(
        total=len(_alerts_store),
        alerts=list(reversed(_alerts_store[-50:])),
    )


# ── WebSocket: Real-time Sensor Simulation ──────────────────────────────────


@app.websocket("/ws/simulate")
async def websocket_simulate(websocket: WebSocket):
    """
    WebSocket endpoint for real-time sensor simulation.
    Generates realistic sensor values every 2 seconds.
    Client receives JSON with current sensor readings plus prediction.
    """
    await websocket.accept()
    _simulation_connections.append(websocket)
    rng = np.random.default_rng()

    # Base sensor values (normal operation)
    base = {
        "temperature_celsius": 52.0,
        "vibration_mms": 2.5,
        "pressure_bar": 5.0,
        "rpm": 1500.0,
        "load_percent": 45.0,
        "voltage_v": 230.0,
        "current_a": 10.0,
        "operating_hours": 5000.0,
    }

    tick = 0
    try:
        while True:
            tick += 1
            # Generate realistic sensor readings with random walk
            sensors = {}
            for name, ideal in base.items():
                noise = rng.normal(0, ideal * 0.02)
                drift = np.sin(tick * 0.1) * ideal * 0.03
                val = ideal + noise + drift
                if name == "operating_hours":
                    val = base["operating_hours"] + tick * 0.5
                sensors[name] = round(max(0, val), 2)

            sensor_data = SensorData(**sensors)
            request = PredictionRequest(
                machine_id="SIM-LIVE",
                tenant_id="simulation",
                sensors=sensor_data,
            )
            prediction = engine.predict(request)
            _machine_store["SIM-LIVE"] = prediction

            payload = {
                "tick": tick,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sensors": sensors,
                "prediction": {
                    "failure_risk_percentage": prediction.failure_risk_percentage,
                    "failure_probability": prediction.failure_probability,
                    "failure_primary_cause": prediction.failure_primary_cause,
                    "failure_type": prediction.failure_type,
                    "confidence_score": prediction.confidence_score,
                    "remaining_useful_life": prediction.remaining_useful_life,
                    "health_score": prediction.health_score,
                    "health_status": prediction.health_status,
                    "risk_level": prediction.risk_level,
                    "maintenance_recommendation": prediction.maintenance_recommendation,
                    "anomalies": [a.model_dump() for a in prediction.anomalies],
                    "feature_importance": prediction.feature_importance,
                },
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2)

    except WebSocketDisconnect:
        logger.info("WebSocket simulation client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)
    finally:
        if websocket in _simulation_connections:
            _simulation_connections.remove(websocket)


# ── Demo Mode ────────────────────────────────────────────────────────────────


async def _run_demo():
    """Simulate a gradual machine failure scenario for demo purposes."""
    global _demo_active
    rng = np.random.default_rng(123)

    machines = {
        "DEMO-PUMP-01": {"type": "pump", "base_temp": 45, "base_vib": 2.0, "degradation": 0.0},
        "DEMO-COMP-02": {"type": "compressor", "base_temp": 50, "base_vib": 3.0, "degradation": 0.0},
        "DEMO-TURB-03": {"type": "turbine", "base_temp": 60, "base_vib": 1.5, "degradation": 0.0},
    }

    tick = 0
    while _demo_active:
        tick += 1
        for mid, m in machines.items():
            # Gradually degrade DEMO-PUMP-01 (the one that will fail)
            if mid == "DEMO-PUMP-01":
                m["degradation"] = min(m["degradation"] + 0.02, 1.0)
            elif mid == "DEMO-TURB-03" and tick > 15:
                m["degradation"] = min(m["degradation"] + 0.03, 1.0)

            d = m["degradation"]
            request = PredictionRequest(
                machine_id=mid,
                tenant_id="demo",
                machine_type=m["type"],
                criticality="high" if d > 0.5 else "medium",
                sensors=SensorData(
                    temperature_celsius=round(m["base_temp"] + d * 50 + rng.normal(0, 2), 1),
                    vibration_mms=round(m["base_vib"] + d * 15 + rng.normal(0, 0.5), 2),
                    pressure_bar=round(5.0 - d * 3 + rng.normal(0, 0.3), 2),
                    rpm=round(1500 + d * 800 + rng.normal(0, 50), 0),
                    load_percent=round(50 + d * 45 + rng.normal(0, 3), 1),
                    voltage_v=round(230 + d * 20 * rng.choice([-1, 1]) + rng.normal(0, 2), 1),
                    current_a=round(10 + d * 12 + rng.normal(0, 1), 1),
                    operating_hours=5000 + tick * 10,
                ),
            )
            pred = engine.predict(request)
            _machine_store[mid] = pred
            _process_alerts(mid, pred)

        await asyncio.sleep(3)


@app.post(
    "/demo/start",
    response_model=DemoResponse,
    tags=["Demo"],
    summary="Start hackathon demo simulation",
)
async def start_demo(
    api_key: str = Depends(require_api_key),
) -> DemoResponse:
    """Start a live demo simulation where machines gradually degrade and fail."""
    global _demo_active, _demo_task

    if _demo_active:
        return DemoResponse(status="already_running", message="Demo simulation is already running")

    _demo_active = True
    _demo_task = asyncio.create_task(_run_demo())
    logger.info("🎬 Demo mode started")

    return DemoResponse(
        status="started",
        message="Demo simulation started. Machines will gradually degrade. Watch the Factory Floor tab!",
    )


@app.post(
    "/demo/stop",
    response_model=DemoResponse,
    tags=["Demo"],
    summary="Stop hackathon demo simulation",
)
async def stop_demo(
    api_key: str = Depends(require_api_key),
) -> DemoResponse:
    """Stop the running demo simulation."""
    global _demo_active, _demo_task

    if not _demo_active:
        return DemoResponse(status="not_running", message="No demo simulation is running")

    _demo_active = False
    if _demo_task and not _demo_task.done():
        _demo_task.cancel()
    logger.info("🛑 Demo mode stopped")

    return DemoResponse(
        status="stopped",
        message="Demo simulation stopped.",
    )


@app.get(
    "/demo/status",
    tags=["Demo"],
)
async def demo_status():
    """Check if demo is currently running."""
    return {"active": _demo_active}


# ── Feedback ─────────────────────────────────────────────────────────────────


@app.post(
    "/feedback",
    response_model=FeedbackResponse,
    tags=["Feedback"],
    summary="Submit operator feedback on a prediction",
    status_code=status.HTTP_200_OK,
)
async def submit_feedback(
    feedback: FeedbackRequest,
    api_key: str = Depends(require_api_key),
) -> FeedbackResponse:
    """Record real-world outcomes for closed-loop learning."""
    try:
        return feedback_store.add_feedback(feedback)
    except Exception as exc:
        logger.exception("Feedback storage failed for prediction=%s", feedback.prediction_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {exc}",
        ) from exc


# ── Model quality ────────────────────────────────────────────────────────────


@app.get(
    "/model_quality",
    response_model=ModelQualityResponse,
    tags=["Operations"],
    summary="Model performance metrics from operator feedback",
)
async def model_quality(
    tenant_id: str | None = None,
    api_key: str = Depends(require_api_key),
) -> ModelQualityResponse:
    """Returns aggregated model-quality metrics."""
    try:
        return feedback_store.get_quality_metrics(tenant_id=tenant_id)
    except Exception as exc:
        logger.exception("Quality metrics computation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Metrics computation error: {exc}",
        ) from exc


# ── Dashboard (frontend) ─────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard() -> HTMLResponse:
    """Serve the interactive prediction dashboard."""
    html_path = _STATIC_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"), status_code=200)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENTRYPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.debug,
        log_level="info",
    )
