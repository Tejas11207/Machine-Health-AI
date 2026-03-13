# Machine-Health-AI
Production-grade FastAPI service with trained Random Forest ML model for industrial predictive maintenance. Monitors 8 key sensors (temperature, vibration, pressure, RPM, load, voltage, current, operating hours) across 5 machine types: pump, compressor, turbine, motor, conveyor.
Readme.md


Machine Health Ai
Production-grade FastAPI service for industrial predictive maintenance using a trained Random Forest ML model.
Features
* Real-time sensor-based failure risk prediction (0-100%) with root cause classification.
* Machine-type-specific profiles (pump, compressor, turbine, motor, conveyor) for thresholds and weights. 
* Anomaly detection, health scores (0-100), remaining useful life estimates, and maintenance recommendations.
* Interactive dashboard with factory floor monitoring, live simulation, CSV batch upload, digital twin visualization. 
* WebSocket real-time simulation, demo mode for gradual machine degradation, operator feedback loop. 
* API key auth, rate limiting, CORS, model quality metrics from feedback.
Tech Stack
Backend: FastAPI, scikit-learn (Random Forest), Pydantic, Uvicorn. Frontend: HTML/CSS/JS, Plotly, vanilla JS.
Quick Start
1. Install dependencies: pip install fastapi uvicorn scikit-learn pydantic numpy.
2. Set API keys in .env: APIKEYS=dev-api-key-001,dev-api-key-002 (comma-separated). 
3. Run server: uvicorn main:app --host 0.0.0.0 --port 8000 --reload. 
4. Open http://localhost:8000 for dashboard; use dev-api-key-001 as API key. 
No external DB needed (SQLite for feedback).
API Endpoints

Endpoint	Method	Description	Auth
/health	GET	Service status and uptime	No
/predictfailure	POST	Single machine prediction	API Key
/predictbatch	POST	Batch (up to 50 machines)	API Key
/uploadcsv	POST	CSV sensor data batch predict	API Key
/machines	GET	Factory dashboard summary	API Key
/alerts	GET	Active sensor alerts	API Key
/ws/simulate	WS	Real-time sensor simulation	API Key
/demostart	POST	Start demo degradation sim	API Key
/feedback	POST	Submit prediction feedback	API Key
/modelquality	GET	Model metrics from feedback	API Key
Request Example (/predictfailure):

json
{
  "machineid": "PUMP-001",
  "tenantid": "plant-a",
  "machinetype": "pump",
  "sensors": {
    "temperaturecelsius": 88.0,
    "vibrationmms": 11.2,
    "pressurebar": 4.1
  }
}
Response includes failureriskpercentage, healthscore, anomalies, etc.
Dashboard Tabs
* Factory Floor: Multi-machine status cards, alerts.
* Predict: Single prediction form with gauges/charts.
* Live Monitor: Real-time sensor sim + trends.
* Upload CSV: Batch from file.
* Digital Twin: SVG machine viz with anomaly highlights.
* Demo: Hackathon sim with degrading machines.
* Batch/Feedback/Quality: Advanced tools.
ML Model Details
* Trained Random Forest (100 trees) on synthetic industrial data (temperature, vibration, etc.). 
* Features: 8 sensors with type-specific ideal/warn/crit thresholds and weights.
* Outputs: Risk via weighted scores + logistic + ML probs; RUL regression; explainable feature importance. 
* Failure modes: bearingwear, overheating, misalignment, etc. 
Structure

text
├── main.py          # FastAPI app, endpoints
├── ml_service.py    # PredictionEngine (RF model)
├── models.py        # Pydantic schemas
├── config.py        # Settings
├── static/          # index.html, app.js, style.css (dashboard)
└── ...             # auth.py, middleware.py
Demo Mode
POST /demostart: Simulates 3 machines degrading over time. Watch Factory Floor for live updates.
Feedback Loop
Submit outcomes via /feedback to compute accuracy, precision, RUL error per tenant.
Production Notes
* Rate limit: 100 req/60s (configurable). 
* In-memory state (machines/alerts); scale with Redis.
* No external deps beyond pip installs; self-contained. 













