/* ═══════════════════════════════════════════════════════════════════════════
   Machine Health AI — Dashboard Application Logic
   Complete with Factory Floor, Live Monitor, CSV Upload, Digital Twin, Demo
   ═══════════════════════════════════════════════════════════════════════════ */

(() => {
    "use strict";

    const API_BASE = window.location.origin;
    const $  = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const apiKeyInput    = $("#api-key-input");
    const healthBadge    = $("#health-badge");
    const healthText     = $("#health-text");
    const toastContainer = $("#toast-container");

    // ── Helpers ───────────────────────────────────────────────────────────

    function getApiKey() { return apiKeyInput.value.trim(); }

    async function apiFetch(path, opts = {}) {
        const key = getApiKey();
        if (!key) { toast("Please enter an API key", "error"); throw new Error("No API key"); }
        const headers = { "Content-Type": "application/json", "X-API-Key": key, ...(opts.headers || {}) };
        const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
        if (!res.ok) {
            let msg = `HTTP ${res.status}`;
            try { const j = await res.json(); msg = j.detail || msg; } catch {}
            throw new Error(msg);
        }
        return res.json();
    }

    function toast(message, type = "info") {
        const el = document.createElement("div");
        el.className = `toast toast-${type}`;
        el.textContent = message;
        toastContainer.appendChild(el);
        setTimeout(() => el.remove(), 4200);
    }

    function formatCause(cause) {
        return cause.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    }

    function riskClass(level) { return `risk-${level}`; }
    function riskBgClass(level) { return `risk-bg-${level}`; }

    function setLoading(btn, loading) {
        btn.classList.toggle("loading", loading);
        btn.disabled = loading;
    }

    function healthColor(score) {
        if (score >= 80) return "var(--green)";
        if (score >= 60) return "var(--amber)";
        if (score >= 40) return "var(--risk-high)";
        return "var(--red)";
    }

    // ── Tab Navigation ────────────────────────────────────────────────────

    $$(".nav-tab").forEach(tab => {
        tab.addEventListener("click", () => {
            $$(".nav-tab").forEach(t => t.classList.remove("active"));
            $$(".tab-content").forEach(t => t.classList.remove("active"));
            tab.classList.add("active");
            $(`#tab-${tab.dataset.tab}`).classList.add("active");
        });
    });

    // ── Health Check ─────────────────────────────────────────────────────

    async function checkHealth() {
        try {
            const data = await fetch(`${API_BASE}/health`).then(r => r.json());
            healthBadge.className = "badge badge-healthy";
            healthText.textContent = `Healthy • ${data.model_version}`;
        } catch {
            healthBadge.className = "badge badge-error";
            healthText.textContent = "Offline";
        }
    }
    checkHealth();
    setInterval(checkHealth, 15000);

    // ═══════════════════════════════════════════════════════════════════════
    //  FACTORY FLOOR TAB
    // ═══════════════════════════════════════════════════════════════════════

    let factoryRefreshInterval = null;

    async function refreshFactory() {
        try {
            const data = await apiFetch("/machines");
            renderFactory(data);
        } catch {}
    }

    function renderFactory(data) {
        $("#f-total").textContent = data.total_machines;
        $("#f-healthy").textContent = data.healthy_count;
        $("#f-warning").textContent = data.warning_count;
        $("#f-critical").textContent = data.critical_count;
        $("#f-avg-health").textContent = data.avg_health_score ? `${data.avg_health_score}%` : "—";

        const grid = $("#factory-machines");
        if (data.machines.length === 0) {
            grid.innerHTML = `<div class="factory-empty-state"><p>🏭 No machines monitored yet.</p><p style="color:var(--text-muted);font-size:0.85rem">Run a prediction, upload CSV, or start Demo mode to add machines.</p></div>`;
            return;
        }

        grid.innerHTML = "";
        data.machines.forEach(m => {
            const card = document.createElement("div");
            card.className = `machine-card status-${m.risk_level}`;
            const hColor = healthColor(m.health_score);
            card.innerHTML = `
                <div class="machine-card-header">
                    <h4>${m.machine_id}</h4>
                    <span class="machine-status-badge ${m.risk_level}">${m.health_status}</span>
                </div>
                <div class="machine-card-health">
                    <div class="mini-health-bar"><div class="mini-health-fill" style="width:${m.health_score}%;background:${hColor}"></div></div>
                    <span class="mini-health-value" style="color:${hColor}">${m.health_score}</span>
                </div>
                <div class="machine-card-details">
                    <div class="machine-card-detail"><span class="label">Risk</span><span class="${riskClass(m.risk_level)}">${m.failure_risk_percentage}%</span></div>
                    <div class="machine-card-detail"><span class="label">RUL</span><span>${m.remaining_useful_life.toLocaleString()}h</span></div>
                    <div class="machine-card-detail"><span class="label">Cause</span><span>${formatCause(m.failure_primary_cause)}</span></div>
                    <div class="machine-card-detail"><span class="label">Anomalies</span><span class="${m.anomaly_count > 0 ? 'risk-critical' : ''}">${m.anomaly_count}</span></div>
                </div>`;
            grid.appendChild(card);
        });
    }

    // Refresh factory when tab is active
    async function refreshAlerts() {
        try {
            const data = await apiFetch("/alerts");
            const panel = $("#factory-alerts");
            if (data.alerts.length === 0) {
                panel.innerHTML = "";
                return;
            }
            panel.innerHTML = data.alerts.slice(0, 6).map(a =>
                `<div class="factory-alert-item ${a.severity}">
                    <span>${a.severity === 'critical' ? '🔴' : '🟡'}</span>
                    <span><strong>${a.machine_id}</strong> — ${a.message}</span>
                </div>`
            ).join("");
        } catch {}
    }

    // Auto-refresh factory floor every 4s
    setInterval(() => {
        if ($("#tab-factory").classList.contains("active")) {
            refreshFactory();
            refreshAlerts();
        }
    }, 4000);

    // Initial load
    setTimeout(() => { refreshFactory(); refreshAlerts(); }, 1000);

    // ═══════════════════════════════════════════════════════════════════════
    //  PREDICT TAB
    // ═══════════════════════════════════════════════════════════════════════

    const predictForm = $("#predict-form");
    const predictBtn  = $("#predict-btn");
    const resultPanel = $("#predict-result");

    predictForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        setLoading(predictBtn, true);
        resultPanel.classList.add("hidden");

        const payload = {
            machine_id: $("#p-machine-id").value.trim(),
            tenant_id: $("#p-tenant-id").value.trim(),
            machine_type: $("#p-machine-type").value,
            criticality: $("#p-criticality").value,
            last_maintenance_days: parseInt($("#p-maint-days").value, 10),
            machine_age_months: parseInt($("#p-age-months").value, 10),
            sensors: {
                temperature_celsius: parseFloat($("#p-temp").value),
                vibration_mms: parseFloat($("#p-vib").value),
                pressure_bar: parseFloat($("#p-pressure").value),
                rpm: parseFloat($("#p-rpm").value),
                load_percent: parseFloat($("#p-load").value),
                voltage_v: parseFloat($("#p-voltage").value),
                current_a: parseFloat($("#p-current").value),
                operating_hours: parseFloat($("#p-hours").value),
            },
        };

        try {
            const data = await apiFetch("/predict_failure", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            renderPrediction(data);
            updateDigitalTwin(data);
            toast("ML Prediction complete", "success");
        } catch (err) {
            toast(err.message, "error");
        } finally {
            setLoading(predictBtn, false);
        }
    });

    function renderPrediction(data) {
        resultPanel.classList.remove("hidden");
        $("#result-pred-id").textContent = data.prediction_id;

        // Health Score Circle
        const healthVal = data.health_score;
        const healthArc = $("#health-arc");
        const maxCircle = 326.7;
        const healthDash = (healthVal / 100) * maxCircle;
        healthArc.style.transition = "stroke-dasharray 1.2s cubic-bezier(0.4,0,0.2,1)";
        healthArc.setAttribute("stroke-dasharray", `${healthDash} ${maxCircle}`);
        const hv = $("#health-value");
        hv.style.color = healthColor(healthVal);
        animateCounter(hv, healthVal, "", "");
        $("#health-status-text").textContent = data.health_status;
        $("#health-status-text").style.color = healthColor(healthVal);

        // Risk Gauge
        const risk = data.failure_risk_percentage;
        const arc = $("#gauge-arc");
        const maxDash = 251.3;
        arc.style.transition = "stroke-dasharray 1s cubic-bezier(0.4,0,0.2,1)";
        arc.setAttribute("stroke-dasharray", `${(risk / 100) * maxDash} ${maxDash}`);
        const gaugeVal = $("#gauge-value");
        animateCounter(gaugeVal, risk, "%", riskClass(data.risk_level));

        // Risk Meter
        const indicator = $("#risk-meter-indicator");
        indicator.style.left = `calc(${risk}% - 10px)`;

        // Result Cards
        $("#result-cause").textContent = formatCause(data.failure_primary_cause);
        $("#result-confidence").textContent = `${data.confidence_score}%`;
        $("#result-confidence").style.color = data.confidence_score >= 70 ? "var(--green)" : data.confidence_score >= 40 ? "var(--amber)" : "var(--red)";
        $("#result-rul").textContent = `${data.remaining_useful_life.toLocaleString()} hrs`;
        const rlEl = $("#result-risk-level");
        rlEl.textContent = data.risk_level.toUpperCase();
        rlEl.className = `result-card-value ${riskClass(data.risk_level)}`;
        $("#result-failure-type").textContent = formatCause(data.failure_type);
        $("#result-fail-prob").textContent = `${(data.failure_probability * 100).toFixed(1)}%`;

        // Anomaly Alerts
        const anomalySection = $("#anomaly-alerts");
        if (data.anomalies && data.anomalies.length > 0) {
            anomalySection.classList.remove("hidden");
            anomalySection.innerHTML = `<h4>⚠ Anomaly Detection (${data.anomalies.length} detected)</h4>` +
                data.anomalies.map(a =>
                    `<div class="anomaly-item ${a.severity}">${a.message}</div>`
                ).join("");
        } else {
            anomalySection.classList.add("hidden");
        }

        // Recommendation
        $("#result-recommendation").textContent = data.maintenance_recommendation;

        // RUL Progress Bar
        const rulPct = Math.min((data.remaining_useful_life / 5000) * 100, 100);
        $("#rul-bar-fill").style.width = `${rulPct}%`;
        $("#rul-bar-value").textContent = `${data.remaining_useful_life.toLocaleString()} hours remaining`;

        // Feature Importance (AI Explainability)
        const container = $("#result-features");
        container.innerHTML = "<h4>🧠 AI Explainability — Feature Importance (Trained Random Forest)</h4>";
        const entries = Object.entries(data.feature_importance || {});
        const maxVal = entries.length ? Math.max(...entries.map(e => e[1])) : 1;
        entries.forEach(([name, val]) => {
            const pct = Math.round((val / maxVal) * 100);
            container.innerHTML += `
                <div class="feature-bar">
                    <span class="feature-name">${name}</span>
                    <div class="feature-track"><div class="feature-fill" style="width:${pct}%"></div></div>
                    <span class="feature-pct">${(val * 100).toFixed(0)}%</span>
                </div>`;
        });

        // Class Probabilities
        const probContainer = $("#result-class-probs");
        const probs = data.class_probabilities || {};
        const probEntries = Object.entries(probs).sort((a, b) => b[1] - a[1]);
        if (probEntries.length > 0) {
            probContainer.innerHTML = "<h4>ML Model Class Probabilities</h4>";
            probEntries.forEach(([cls, prob]) => {
                const pct = (prob * 100).toFixed(1);
                probContainer.innerHTML += `
                    <div class="class-prob-bar">
                        <span class="class-prob-name">${formatCause(cls)}</span>
                        <div class="class-prob-track"><div class="class-prob-fill" style="width:${pct}%"></div></div>
                        <span class="class-prob-pct">${pct}%</span>
                    </div>`;
            });
        }
    }

    function animateCounter(el, target, suffix, colorClass) {
        if (colorClass) el.className = `gauge-value ${colorClass}`;
        let current = 0;
        const step = target / 40;
        const interval = setInterval(() => {
            current += step;
            if (current >= target) { current = target; clearInterval(interval); }
            el.textContent = current.toFixed(1) + suffix;
        }, 20);
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  LIVE MONITOR TAB — Client-side simulation from user input
    // ═══════════════════════════════════════════════════════════════════════

    let liveInterval = null;
    const liveHistory = { timestamps: [], temp: [], vib: [], pressure: [], rpm: [], risk: [], health: [] };
    const MAX_HISTORY = 60;

    const sensorLimits = {
        temperature_celsius: { min: -10, max: 95 },
        vibration_mms: { min: 0, max: 15 },
        pressure_bar: { min: 0.5, max: 12 },
        rpm: { min: 300, max: 3500 },
        load_percent: { min: 0, max: 100 },
        voltage_v: { min: 190, max: 270 },
        current_a: { min: 0.5, max: 25 },
        operating_hours: { min: 0, max: 30000 },
    };

    const gaugeMap = {
        temperature_celsius: { val: "#lg-temp", fill: "#lgf-temp" },
        vibration_mms: { val: "#lg-vib", fill: "#lgf-vib" },
        pressure_bar: { val: "#lg-pressure", fill: "#lgf-pressure" },
        rpm: { val: "#lg-rpm", fill: "#lgf-rpm" },
        load_percent: { val: "#lg-load", fill: "#lgf-load" },
        voltage_v: { val: "#lg-voltage", fill: "#lgf-voltage" },
        current_a: { val: "#lg-current", fill: "#lgf-current" },
        operating_hours: { val: "#lg-hours", fill: "#lgf-hours" },
    };

    // Read base sensor values from the Predict form
    function getBaseValuesFromForm() {
        return {
            machine_id: $("#p-machine-id").value.trim() || "LIVE-SIM",
            tenant_id: $("#p-tenant-id").value.trim() || "live",
            machine_type: $("#p-machine-type").value || "general",
            criticality: $("#p-criticality").value || "medium",
            last_maintenance_days: parseInt($("#p-maint-days").value, 10) || 30,
            machine_age_months: parseInt($("#p-age-months").value, 10) || 24,
            sensors: {
                temperature_celsius: parseFloat($("#p-temp").value) || 65,
                vibration_mms: parseFloat($("#p-vib").value) || 3.5,
                pressure_bar: parseFloat($("#p-pressure").value) || 5.0,
                rpm: parseFloat($("#p-rpm").value) || 1500,
                load_percent: parseFloat($("#p-load").value) || 50,
                voltage_v: parseFloat($("#p-voltage").value) || 230,
                current_a: parseFloat($("#p-current").value) || 10,
                operating_hours: parseFloat($("#p-hours").value) || 5000,
            },
        };
    }

    // Add noise within ±10% of the base value, clamped to sensor limits
    function addNoise(base, sensorName) {
        const noise = (Math.random() - 0.5) * 2 * base * 0.10;
        let val = base + noise;
        const limit = sensorLimits[sensorName];
        if (limit) {
            val = Math.max(limit.min, Math.min(limit.max, val));
        }
        return parseFloat(val.toFixed(2));
    }

    // Run one tick of the live simulation
    async function liveSimTick() {
        const base = getBaseValuesFromForm();

        // Generate noisy sensor data around user's input
        const sensors = {};
        for (const [name, baseVal] of Object.entries(base.sensors)) {
            sensors[name] = addNoise(baseVal, name);
        }
        // Operating hours always increment slightly
        sensors.operating_hours = parseFloat((base.sensors.operating_hours + Math.random() * 2).toFixed(1));

        const payload = {
            machine_id: base.machine_id + "-LIVE",
            tenant_id: base.tenant_id,
            machine_type: base.machine_type,
            criticality: base.criticality,
            last_maintenance_days: base.last_maintenance_days,
            machine_age_months: base.machine_age_months,
            sensors: sensors,
        };

        try {
            const prediction = await apiFetch("/predict_failure", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            updateLiveGauges(sensors, prediction);
            updateLivePrediction(prediction);
            updateTrendCharts({ timestamp: new Date().toISOString(), sensors, prediction });
            updateDigitalTwinFromLive({ sensors, prediction });
        } catch (err) {
            // silently ignore — don't spam errors during live mode
        }
    }

    $("#live-start-btn").addEventListener("click", () => {
        if (liveInterval) return;

        $("#live-status").textContent = "🟢 Live — Simulating";
        $("#live-start-btn").disabled = true;
        $("#live-stop-btn").disabled = false;
        $("#live-prediction").style.display = "";
        $("#live-input-hint").style.display = "";
        toast("Live monitoring started — using your Predict form values", "success");

        // Clear old history
        Object.keys(liveHistory).forEach(k => liveHistory[k] = []);

        // Run first tick immediately, then every 5 seconds
        liveSimTick();
        liveInterval = setInterval(liveSimTick, 5000);
    });

    $("#live-stop-btn").addEventListener("click", () => {
        if (liveInterval) { clearInterval(liveInterval); liveInterval = null; }
        $("#live-status").textContent = "⚪ Stopped";
        $("#live-start-btn").disabled = false;
        $("#live-stop-btn").disabled = true;
        $("#live-input-hint").style.display = "none";
        toast("Live monitoring stopped", "info");
    });

    function updateLiveGauges(sensors, prediction) {
        for (const [name, value] of Object.entries(sensors)) {
            const g = gaugeMap[name];
            if (!g) continue;

            const valEl = $(g.val);
            const fillEl = $(g.fill);
            const limit = sensorLimits[name];

            valEl.textContent = typeof value === "number" ? value.toFixed(1) : value;
            const pct = Math.min(((value - limit.min) / (limit.max - limit.min)) * 100, 100);
            fillEl.style.width = `${pct}%`;

            // Color based on anomaly
            const card = valEl.closest(".live-gauge-card");
            const isAnomaly = prediction.anomalies && prediction.anomalies.some(a => a.sensor === name);
            card.classList.toggle("anomaly", isAnomaly);
            if (pct > 85) {
                fillEl.style.background = "var(--red)";
                valEl.style.color = "var(--red)";
            } else if (pct > 65) {
                fillEl.style.background = "var(--amber)";
                valEl.style.color = "var(--amber)";
            } else {
                fillEl.style.background = "var(--accent)";
                valEl.style.color = "var(--text-primary)";
            }
        }
    }

    function updateLivePrediction(pred) {
        $("#lp-risk").textContent = pred.failure_risk_percentage + "%";
        $("#lp-risk").className = riskClass(pred.risk_level);
        $("#lp-health").textContent = pred.health_score + "/100";
        $("#lp-health").style.color = healthColor(pred.health_score);
        $("#lp-cause").textContent = formatCause(pred.failure_primary_cause);
        $("#lp-rul").textContent = pred.remaining_useful_life.toLocaleString() + " hrs";
        $("#lp-conf").textContent = pred.confidence_score + "%";
        $("#lp-status").textContent = pred.health_status || pred.risk_level;
        $("#lp-status").className = riskClass(pred.risk_level);
    }

    function updateTrendCharts(data) {
        const time = new Date(data.timestamp).toLocaleTimeString();
        liveHistory.timestamps.push(time);
        liveHistory.temp.push(data.sensors.temperature_celsius);
        liveHistory.vib.push(data.sensors.vibration_mms);
        liveHistory.pressure.push(data.sensors.pressure_bar);
        liveHistory.rpm.push(data.sensors.rpm);
        liveHistory.risk.push(data.prediction.failure_risk_percentage);
        liveHistory.health.push(data.prediction.health_score);

        if (liveHistory.timestamps.length > MAX_HISTORY) {
            Object.keys(liveHistory).forEach(k => liveHistory[k].shift());
        }

        const layoutBase = {
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#8b95a8", family: "Inter", size: 11 },
            margin: { l: 45, r: 15, t: 35, b: 30 },
            xaxis: { showgrid: false, tickangle: -45, tickfont: { size: 9 } },
            yaxis: { gridcolor: "rgba(255,255,255,0.04)", tickfont: { size: 10 } },
        };

        const config = { responsive: true, displayModeBar: false };

        // ── Easy-to-read zone helpers ────────────────────────────────
        // Colored background bands: green = SAFE, yellow = WARNING, red = DANGER
        function zoneRect(y0, y1, color) {
            return {
                type: "rect", xref: "paper", x0: 0, x1: 1, y0, y1,
                fillcolor: color, line: { width: 0 }, layer: "below",
            };
        }
        const SAFE   = "rgba(34,197,94,0.08)";
        const WARN   = "rgba(245,158,11,0.12)";
        const DANGER = "rgba(239,68,68,0.12)";

        // Current-value badge pinned top-right
        function curVal(val, unit) {
            return {
                xref: "paper", yref: "paper", x: 0.98, y: 0.92,
                text: `<b>${val}${unit}</b>`, showarrow: false,
                font: { size: 16, color: "#e2e8f0", family: "Inter" },
                bgcolor: "rgba(15,20,25,0.7)", borderpad: 4,
                bordercolor: "rgba(255,255,255,0.1)", borderwidth: 1,
            };
        }

        // Readable layout
        const ezLayout = {
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#94a3b8", family: "Inter", size: 12 },
            margin: { l: 50, r: 20, t: 45, b: 30 },
            xaxis: { showgrid: false, tickangle: -45, tickfont: { size: 9 } },
            yaxis: { gridcolor: "rgba(255,255,255,0.06)", tickfont: { size: 11 }, zeroline: false },
            showlegend: false,
        };

        if (typeof Plotly !== "undefined") {
            const last = (a) => a.length ? a[a.length - 1] : 0;

            // 🌡️ Temperature
            Plotly.react("chart-temp", [{
                x: liveHistory.timestamps, y: liveHistory.temp,
                type: "scatter", mode: "lines+markers",
                line: { color: "#3b82f6", width: 3, shape: "spline" },
                marker: { size: 5 },
                fill: "tozeroy", fillcolor: "rgba(59,130,246,0.06)",
            }], { ...ezLayout,
                title: { text: "\ud83c\udf21\ufe0f Temperature (\u00b0C)", font: { size: 14, color: "#e2e8f0" } },
                yaxis: { ...ezLayout.yaxis, range: [0, 120] },
                shapes: [ zoneRect(0,75,SAFE), zoneRect(75,95,WARN), zoneRect(95,120,DANGER) ],
                annotations: [ curVal(last(liveHistory.temp).toFixed(1), "\u00b0C") ],
            }, config);

            // 📳 Vibration
            Plotly.react("chart-vib", [{
                x: liveHistory.timestamps, y: liveHistory.vib,
                type: "scatter", mode: "lines+markers",
                line: { color: "#8b5cf6", width: 3, shape: "spline" },
                marker: { size: 5 },
                fill: "tozeroy", fillcolor: "rgba(139,92,246,0.06)",
            }], { ...ezLayout,
                title: { text: "\ud83d\udcf3 Vibration (mm/s)", font: { size: 14, color: "#e2e8f0" } },
                yaxis: { ...ezLayout.yaxis, range: [0, 20] },
                shapes: [ zoneRect(0,7,SAFE), zoneRect(7,15,WARN), zoneRect(15,20,DANGER) ],
                annotations: [ curVal(last(liveHistory.vib).toFixed(1), " mm/s") ],
            }, config);

            // 💨 Pressure (too low or too high is bad)
            Plotly.react("chart-pressure", [{
                x: liveHistory.timestamps, y: liveHistory.pressure,
                type: "scatter", mode: "lines+markers",
                line: { color: "#0ea5e9", width: 3, shape: "spline" },
                marker: { size: 5 },
                fill: "tozeroy", fillcolor: "rgba(14,165,233,0.06)",
            }], { ...ezLayout,
                title: { text: "\ud83d\udca8 Pressure (bar)", font: { size: 14, color: "#e2e8f0" } },
                yaxis: { ...ezLayout.yaxis, range: [0, 15] },
                shapes: [ zoneRect(0,2,DANGER), zoneRect(2,3,WARN), zoneRect(3,8,SAFE), zoneRect(8,12,WARN), zoneRect(12,15,DANGER) ],
                annotations: [ curVal(last(liveHistory.pressure).toFixed(1), " bar") ],
            }, config);

            // ⚙️ RPM
            Plotly.react("chart-rpm", [{
                x: liveHistory.timestamps, y: liveHistory.rpm,
                type: "scatter", mode: "lines+markers",
                line: { color: "#64748b", width: 3, shape: "spline" },
                marker: { size: 5 },
                fill: "tozeroy", fillcolor: "rgba(100,116,139,0.06)",
            }], { ...ezLayout,
                title: { text: "\u2699\ufe0f RPM", font: { size: 14, color: "#e2e8f0" } },
                yaxis: { ...ezLayout.yaxis, range: [0, 4000] },
                shapes: [ zoneRect(0,2200,SAFE), zoneRect(2200,3500,WARN), zoneRect(3500,4000,DANGER) ],
                annotations: [ curVal(Math.round(last(liveHistory.rpm)), " RPM") ],
            }, config);

            // ⚠️ Failure Risk
            Plotly.react("chart-risk", [{
                x: liveHistory.timestamps, y: liveHistory.risk,
                type: "scatter", mode: "lines+markers",
                line: { color: "#ef4444", width: 3, shape: "spline" },
                marker: { size: 5 },
            }], { ...ezLayout,
                title: { text: "\u26a0\ufe0f Failure Risk (%)", font: { size: 14, color: "#e2e8f0" } },
                yaxis: { ...ezLayout.yaxis, range: [0, 100] },
                shapes: [ zoneRect(0,30,SAFE), zoneRect(30,55,WARN), zoneRect(55,80,"rgba(249,115,22,0.12)"), zoneRect(80,100,DANGER) ],
                annotations: [ curVal(last(liveHistory.risk).toFixed(1), "%") ],
            }, config);

            // 💚 Health Score (inverted — high is GOOD)
            Plotly.react("chart-health", [{
                x: liveHistory.timestamps, y: liveHistory.health,
                type: "scatter", mode: "lines+markers",
                line: { color: "#22c55e", width: 3, shape: "spline" },
                marker: { size: 5 },
            }], { ...ezLayout,
                title: { text: "\ud83d\udc9a Health Score", font: { size: 14, color: "#e2e8f0" } },
                yaxis: { ...ezLayout.yaxis, range: [0, 100] },
                shapes: [ zoneRect(0,40,DANGER), zoneRect(40,60,WARN), zoneRect(60,80,"rgba(245,158,11,0.06)"), zoneRect(80,100,SAFE) ],
                annotations: [ curVal(Math.round(last(liveHistory.health)), "/100") ],
            }, config);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  CSV UPLOAD TAB
    // ═══════════════════════════════════════════════════════════════════════

    const csvDropzone = $("#csv-dropzone");
    const csvFileInput = $("#csv-file-input");
    const csvResult = $("#csv-result");

    $("#csv-browse-btn").addEventListener("click", () => csvFileInput.click());
    csvDropzone.addEventListener("click", (e) => {
        if (e.target.tagName !== "BUTTON") csvFileInput.click();
    });

    csvDropzone.addEventListener("dragover", (e) => { e.preventDefault(); csvDropzone.classList.add("dragover"); });
    csvDropzone.addEventListener("dragleave", () => csvDropzone.classList.remove("dragover"));
    csvDropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        csvDropzone.classList.remove("dragover");
        const file = e.dataTransfer.files[0];
        if (file) uploadCSV(file);
    });

    csvFileInput.addEventListener("change", () => {
        if (csvFileInput.files[0]) uploadCSV(csvFileInput.files[0]);
    });

    async function uploadCSV(file) {
        if (!file.name.endsWith(".csv")) {
            toast("Please upload a CSV file", "error");
            return;
        }

        const key = getApiKey();
        if (!key) { toast("Please enter an API key", "error"); return; }

        toast(`Uploading ${file.name}...`, "info");
        csvResult.classList.add("hidden");

        const formData = new FormData();
        formData.append("file", file);

        try {
            const res = await fetch(`${API_BASE}/upload_csv`, {
                method: "POST",
                headers: { "X-API-Key": key },
                body: formData,
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            const data = await res.json();
            renderCSVResult(data);
            toast(`${data.rows_processed} rows processed successfully`, "success");
        } catch (err) {
            toast(err.message, "error");
        }
    }

    function renderCSVResult(data) {
        csvResult.classList.remove("hidden");
        let html = `
            <div class="card glass" style="margin-top:20px">
                <h3 style="margin-bottom:16px">📊 CSV Upload Results — ${data.filename}</h3>
                <div class="batch-summary card glass" style="margin-bottom:16px">
                    <div class="batch-stat"><div class="batch-stat-value">${data.rows_processed}</div><div class="batch-stat-label">Rows</div></div>
                    <div class="batch-stat"><div class="batch-stat-value">${data.processing_time_ms.toFixed(1)}ms</div><div class="batch-stat-label">Latency</div></div>
                </div>
                <div id="csv-cards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px">`;

        data.predictions.forEach(p => {
            html += `
                <div class="batch-card">
                    <div class="batch-card-risk ${riskBgClass(p.risk_level)}">${p.failure_risk_percentage}%</div>
                    <h4>${p.machine_id}</h4>
                    <div class="batch-card-row"><span class="label">Health</span><span style="color:${healthColor(p.health_score)}">${p.health_score}/100 — ${p.health_status}</span></div>
                    <div class="batch-card-row"><span class="label">Cause</span><span>${formatCause(p.failure_primary_cause)}</span></div>
                    <div class="batch-card-row"><span class="label">Confidence</span><span>${p.confidence_score}%</span></div>
                    <div class="batch-card-row"><span class="label">RUL</span><span>${p.remaining_useful_life.toLocaleString()} hrs</span></div>
                    <div class="batch-card-row"><span class="label">Risk Level</span><span class="${riskClass(p.risk_level)}">${p.risk_level.toUpperCase()}</span></div>
                    ${p.anomalies.length > 0 ? `<div style="margin-top:8px;font-size:0.78rem;color:var(--red)">⚠ ${p.anomalies.length} anomal${p.anomalies.length > 1 ? 'ies' : 'y'} detected</div>` : ''}
                    <div style="margin-top:8px;font-size:0.8rem;color:var(--text-secondary)">${p.maintenance_recommendation}</div>
                </div>`;
        });

        html += `</div></div>`;
        csvResult.innerHTML = html;
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  DIGITAL TWIN
    // ═══════════════════════════════════════════════════════════════════════

    function updateDigitalTwin(data) {
        // Update sensor values on SVG
        const s = data.sensors || {};
        if (s.temperature_celsius !== undefined) $("#twin-temp-val").textContent = `${s.temperature_celsius}°C`;
        if (s.vibration_mms !== undefined) $("#twin-vib-val").textContent = `${s.vibration_mms}mm/s`;
        if (s.rpm !== undefined) $("#twin-rpm-val").textContent = `${s.rpm}RPM`;
        if (s.load_percent !== undefined) $("#twin-load-val").textContent = `${s.load_percent}%`;
        if (s.pressure_bar !== undefined) $("#twin-pressure-val").textContent = `${s.pressure_bar}bar`;

        // Status panel
        $("#twin-health").textContent = `${data.health_score}/100 — ${data.health_status}`;
        $("#twin-health").style.color = healthColor(data.health_score);
        $("#twin-risk").textContent = data.risk_level.toUpperCase();
        $("#twin-risk").className = riskClass(data.risk_level);
        $("#twin-cause").textContent = formatCause(data.failure_primary_cause);
        $("#twin-rul").textContent = `${data.remaining_useful_life.toLocaleString()} hrs`;

        // Highlight anomalous sensors on twin
        const anomalySensors = (data.anomalies || []).map(a => a.sensor);
        highlightTwinSensor("twin-sensor-temp", anomalySensors.includes("temperature_celsius"));
        highlightTwinSensor("twin-sensor-vib", anomalySensors.includes("vibration_mms"));
        highlightTwinSensor("twin-sensor-rpm", anomalySensors.includes("rpm"));
        highlightTwinSensor("twin-sensor-load", anomalySensors.includes("load_percent"));
        highlightTwinSensor("twin-sensor-pressure", anomalySensors.includes("pressure_bar"));

        // Rotor animation based on risk
        const rotor = $("#twin-rotor");
        if (data.risk_level === "critical") {
            rotor.style.fill = "rgba(239,68,68,0.2)";
            rotor.style.stroke = "var(--red)";
        } else if (data.risk_level === "high") {
            rotor.style.fill = "rgba(249,115,22,0.15)";
            rotor.style.stroke = "var(--risk-high)";
        } else {
            rotor.style.fill = "rgba(59,130,246,0.1)";
            rotor.style.stroke = "var(--accent)";
        }
    }

    function updateDigitalTwinFromLive(data) {
        const twinData = {
            sensors: data.sensors,
            health_score: data.prediction.health_score,
            health_status: data.prediction.health_status || "",
            risk_level: data.prediction.risk_level,
            failure_primary_cause: data.prediction.failure_primary_cause,
            remaining_useful_life: data.prediction.remaining_useful_life,
            anomalies: data.prediction.anomalies || [],
        };
        updateDigitalTwin(twinData);
    }

    function highlightTwinSensor(groupId, isAnomalous) {
        const g = $(`#${groupId}`);
        if (!g) return;
        if (isAnomalous) {
            g.classList.add("twin-sensor-pulse");
            g.querySelector("circle").style.stroke = "var(--red)";
            g.querySelector("circle").style.fill = "rgba(239,68,68,0.3)";
        } else {
            g.classList.remove("twin-sensor-pulse");
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  DEMO MODE
    // ═══════════════════════════════════════════════════════════════════════

    const demoStartBtn = $("#demo-start-btn");
    const demoStopBtn = $("#demo-stop-btn");
    const demoStatus = $("#demo-status");
    const demoLog = $("#demo-log");
    const demoLogEntries = $("#demo-log-entries");
    let demoRefreshInterval = null;

    demoStartBtn.addEventListener("click", async () => {
        setLoading(demoStartBtn, true);
        try {
            const data = await apiFetch("/demo/start", { method: "POST" });
            demoStatus.innerHTML = `<span class="demo-status-dot" style="background:var(--green);box-shadow:0 0 8px var(--green)"></span><span>${data.message}</span>`;
            demoStatus.classList.add("active");
            demoStartBtn.disabled = true;
            demoStopBtn.disabled = false;
            demoLog.style.display = "";
            toast("🎬 Demo simulation started!", "success");

            // Start polling factory floor
            demoRefreshInterval = setInterval(async () => {
                await refreshFactory();
                await refreshAlerts();
                addDemoLogEntry();
            }, 4000);
        } catch (err) {
            toast(err.message, "error");
        } finally {
            setLoading(demoStartBtn, false);
        }
    });

    demoStopBtn.addEventListener("click", async () => {
        setLoading(demoStopBtn, true);
        try {
            const data = await apiFetch("/demo/stop", { method: "POST" });
            demoStatus.innerHTML = `<span class="demo-status-dot"></span><span>${data.message}</span>`;
            demoStatus.classList.remove("active");
            demoStartBtn.disabled = false;
            demoStopBtn.disabled = true;
            if (demoRefreshInterval) { clearInterval(demoRefreshInterval); demoRefreshInterval = null; }
            toast("Demo stopped", "info");
        } catch (err) {
            toast(err.message, "error");
        } finally {
            setLoading(demoStopBtn, false);
        }
    });

    function addDemoLogEntry() {
        const now = new Date().toLocaleTimeString();
        const entry = document.createElement("div");
        entry.className = "demo-log-entry";
        entry.textContent = `[${now}] Factory floor refreshed — monitoring active`;
        demoLogEntries.insertBefore(entry, demoLogEntries.firstChild);
        if (demoLogEntries.children.length > 30) {
            demoLogEntries.removeChild(demoLogEntries.lastChild);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  BATCH TAB
    // ═══════════════════════════════════════════════════════════════════════

    const batchList = [];
    const batchJson       = $("#batch-json");
    const batchSubmitBtn  = $("#batch-submit-btn");
    const batchSubmitJson = $("#batch-submit-json-btn");
    const batchResult     = $("#batch-result");

    const PRESETS = {
        pump:       { criticality: "high",     machine_type: "pump",       sensors: { temperature_celsius: 88, vibration_mms: 11,   pressure_bar: 4, rpm: 1800, load_percent: 82, voltage_v: 228, current_a: 16, operating_hours: 12000 } },
        compressor: { criticality: "medium",   machine_type: "compressor", sensors: { temperature_celsius: 55, vibration_mms: 3,    pressure_bar: 5, rpm: 1450, load_percent: 45, voltage_v: 232, current_a: 8,  operating_hours: 3000  } },
        conveyor:   { criticality: "low",      machine_type: "conveyor",   sensors: { temperature_celsius: 42, vibration_mms: 1.5,  pressure_bar: 5, rpm: 1200, load_percent: 30, voltage_v: 230, current_a: 6,  operating_hours: 800   } },
        turbine:    { criticality: "critical",  machine_type: "turbine",   sensors: { temperature_celsius: 97, vibration_mms: 18,   pressure_bar: 2, rpm: 2800, load_percent: 95, voltage_v: 245, current_a: 22, operating_hours: 28000 } },
        motor:      { criticality: "medium",   machine_type: "motor",      sensors: { temperature_celsius: 60, vibration_mms: 4,    pressure_bar: 5, rpm: 1500, load_percent: 55, voltage_v: 230, current_a: 12, operating_hours: 6000  } },
    };
    const presetCounters = { pump: 0, compressor: 0, conveyor: 0, turbine: 0, motor: 0 };

    // Mode toggle
    $$("#batch-mode-form, #batch-mode-json").forEach(btn => {
        btn.addEventListener("click", () => {
            $$("#batch-mode-form, #batch-mode-json").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            const mode = btn.dataset.mode;
            $("#batch-form-mode").style.display = mode === "form" ? "" : "none";
            $("#batch-json-mode").style.display = mode === "json" ? "" : "none";
        });
    });

    // Presets
    $$(".preset-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const type = btn.dataset.preset;
            const preset = PRESETS[type];
            presetCounters[type]++;
            const id = `${type.toUpperCase()}-${String(presetCounters[type]).padStart(2, "0")}`;
            batchList.push({
                machine_id: id, tenant_id: "plant_a",
                criticality: preset.criticality, machine_type: preset.machine_type,
                sensors: { ...preset.sensors },
            });
            renderBatchTable();
            toast(`${id} added to batch`, "success");
            btn.classList.add("preset-clicked");
            setTimeout(() => btn.classList.remove("preset-clicked"), 400);
        });
    });

    // Add machine
    $("#batch-add-btn").addEventListener("click", () => {
        const machineId = $("#b-machine-id").value.trim();
        const tenantId  = $("#b-tenant-id").value.trim();
        if (!machineId) { toast("Machine ID is required", "error"); return; }
        if (!tenantId)  { toast("Tenant ID is required", "error"); return; }
        batchList.push({
            machine_id: machineId, tenant_id: tenantId,
            criticality: $("#b-criticality").value, machine_type: $("#b-machine-type").value,
            sensors: {
                temperature_celsius: parseFloat($("#b-temp").value) || 65,
                vibration_mms: parseFloat($("#b-vib").value) || 3.5,
                pressure_bar: parseFloat($("#b-pressure").value) || 5,
                rpm: parseFloat($("#b-rpm").value) || 1500,
                load_percent: parseFloat($("#b-load").value) || 50,
                voltage_v: parseFloat($("#b-voltage").value) || 230,
                current_a: parseFloat($("#b-current").value) || 10,
                operating_hours: parseFloat($("#b-hours").value) || 5000,
            },
        });
        renderBatchTable();
        toast(`${machineId} added`, "success");
        const match = machineId.match(/^(.+?)(\d+)$/);
        if (match) {
            const nextNum = parseInt(match[2], 10) + 1;
            $("#b-machine-id").value = match[1] + String(nextNum).padStart(match[2].length, "0");
        } else {
            $("#b-machine-id").value = "";
        }
    });

    // Clear
    $("#batch-clear-form").addEventListener("click", () => {
        $("#b-machine-id").value = ""; $("#b-tenant-id").value = "plant_a";
        $("#b-criticality").value = "medium"; $("#b-machine-type").value = "general";
        $("#b-temp").value = "65"; $("#b-vib").value = "3.5"; $("#b-pressure").value = "5.0";
        $("#b-rpm").value = "1500"; $("#b-load").value = "50"; $("#b-voltage").value = "230";
        $("#b-current").value = "10"; $("#b-hours").value = "5000";
    });

    $("#batch-clear-all").addEventListener("click", () => {
        batchList.length = 0; renderBatchTable();
        toast("Batch list cleared", "info");
    });

    function renderBatchTable() {
        const card = $("#batch-list-card");
        const tbody = $("#batch-table-body");
        const count = $("#batch-count");
        if (batchList.length === 0) { card.style.display = "none"; return; }
        card.style.display = "";
        count.textContent = batchList.length;
        tbody.innerHTML = "";
        batchList.forEach((entry, idx) => {
            const s = entry.sensors;
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${idx + 1}</td><td><strong>${entry.machine_id}</strong></td><td>${entry.tenant_id}</td>
                <td><span class="crit-badge crit-${entry.criticality}">${entry.criticality}</span></td>
                <td>${s.temperature_celsius}°C</td><td>${s.vibration_mms}</td><td>${s.rpm}</td><td>${s.load_percent}%</td>
                <td><button class="btn-remove-row" data-idx="${idx}" title="Remove">✕</button></td>`;
            tbody.appendChild(tr);
        });
        tbody.querySelectorAll(".btn-remove-row").forEach(btn => {
            btn.addEventListener("click", () => {
                const removed = batchList.splice(parseInt(btn.dataset.idx, 10), 1)[0];
                renderBatchTable();
                toast(`${removed.machine_id} removed`, "info");
            });
        });
    }

    // Submit from form
    batchSubmitBtn.addEventListener("click", async () => {
        if (batchList.length === 0) { toast("Add at least one machine", "error"); return; }
        setLoading(batchSubmitBtn, true);
        batchResult.classList.add("hidden");
        try {
            const data = await apiFetch("/predict_batch", { method: "POST", body: JSON.stringify({ requests: batchList.map(e => ({ ...e })) }) });
            renderBatch(data);
            toast(`Batch complete — ${data.total} machines`, "success");
        } catch (err) { toast(err.message, "error"); }
        finally { setLoading(batchSubmitBtn, false); }
    });

    // JSON mode
    $("#batch-load-sample").addEventListener("click", () => {
        batchJson.value = JSON.stringify({
            requests: [
                { machine_id: "PUMP-01",  tenant_id: "plant_a", criticality: "high",   machine_type: "pump",       sensors: { temperature_celsius: 88, vibration_mms: 11, pressure_bar: 4, rpm: 1800, load_percent: 82, voltage_v: 228, current_a: 16, operating_hours: 12000 } },
                { machine_id: "COMP-02",  tenant_id: "plant_a", criticality: "medium", machine_type: "compressor", sensors: { temperature_celsius: 55, vibration_mms: 3,  pressure_bar: 5, rpm: 1450, load_percent: 45, voltage_v: 232, current_a: 8,  operating_hours: 3000  } },
                { machine_id: "CONV-03",  tenant_id: "plant_b", criticality: "low",    machine_type: "conveyor",   sensors: { temperature_celsius: 42, vibration_mms: 1.5,pressure_bar: 5, rpm: 1200, load_percent: 30, voltage_v: 230, current_a: 6,  operating_hours: 800   } },
                { machine_id: "TURB-04",  tenant_id: "plant_b", criticality: "critical",machine_type: "turbine",   sensors: { temperature_celsius: 97, vibration_mms: 18, pressure_bar: 2, rpm: 2800, load_percent: 95, voltage_v: 245, current_a: 22, operating_hours: 28000 } },
            ],
        }, null, 2);
        toast("Sample data loaded", "info");
    });

    batchSubmitJson.addEventListener("click", async () => {
        setLoading(batchSubmitJson, true);
        batchResult.classList.add("hidden");
        let payload;
        try { payload = JSON.parse(batchJson.value); } catch {
            toast("Invalid JSON", "error"); setLoading(batchSubmitJson, false); return;
        }
        try {
            const data = await apiFetch("/predict_batch", { method: "POST", body: JSON.stringify(payload) });
            renderBatch(data);
            toast(`Batch complete — ${data.total} machines`, "success");
        } catch (err) { toast(err.message, "error"); }
        finally { setLoading(batchSubmitJson, false); }
    });

    function renderBatch(data) {
        batchResult.classList.remove("hidden");
        const predictions = data.predictions;
        const avgRisk = (predictions.reduce((s, p) => s + p.failure_risk_percentage, 0) / predictions.length).toFixed(1);
        const critical = predictions.filter(p => p.risk_level === "critical").length;
        const high = predictions.filter(p => p.risk_level === "high").length;
        const avgHealth = (predictions.reduce((s, p) => s + p.health_score, 0) / predictions.length).toFixed(0);

        $("#batch-summary").innerHTML = `
            <div class="batch-stat"><div class="batch-stat-value">${data.total}</div><div class="batch-stat-label">Machines</div></div>
            <div class="batch-stat"><div class="batch-stat-value">${avgRisk}%</div><div class="batch-stat-label">Avg Risk</div></div>
            <div class="batch-stat"><div class="batch-stat-value" style="color:${healthColor(parseInt(avgHealth))}">${avgHealth}</div><div class="batch-stat-label">Avg Health</div></div>
            <div class="batch-stat"><div class="batch-stat-value risk-critical">${critical}</div><div class="batch-stat-label">Critical</div></div>
            <div class="batch-stat"><div class="batch-stat-value risk-high">${high}</div><div class="batch-stat-label">High Risk</div></div>
            <div class="batch-stat"><div class="batch-stat-value">${data.processing_time_ms.toFixed(1)}ms</div><div class="batch-stat-label">Latency</div></div>`;

        const cardsContainer = $("#batch-cards");
        cardsContainer.innerHTML = "";
        predictions.forEach(p => {
            const card = document.createElement("div");
            card.className = "batch-card";
            card.innerHTML = `
                <div class="batch-card-risk ${riskBgClass(p.risk_level)}">${p.failure_risk_percentage}%</div>
                <h4>${p.machine_id}</h4>
                <div class="batch-card-row"><span class="label">Health</span><span style="color:${healthColor(p.health_score)}">${p.health_score}/100</span></div>
                <div class="batch-card-row"><span class="label">Cause</span><span>${formatCause(p.failure_primary_cause)}</span></div>
                <div class="batch-card-row"><span class="label">Confidence</span><span>${p.confidence_score}%</span></div>
                <div class="batch-card-row"><span class="label">RUL</span><span>${p.remaining_useful_life.toLocaleString()} hrs</span></div>
                <div class="batch-card-row"><span class="label">Risk</span><span class="${riskClass(p.risk_level)}">${p.risk_level.toUpperCase()}</span></div>
                ${p.anomalies.length > 0 ? `<div style="margin-top:6px;font-size:0.78rem;color:var(--red)">⚠ ${p.anomalies.length} anomalies</div>` : ''}
                <div style="margin-top:10px;font-size:0.82rem;color:var(--text-secondary)">${p.maintenance_recommendation}</div>`;
            cardsContainer.appendChild(card);
        });
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  FEEDBACK TAB
    // ═══════════════════════════════════════════════════════════════════════

    const feedbackForm = $("#feedback-form");
    const feedbackBtn  = $("#feedback-btn");
    const feedbackResult = $("#feedback-result");

    feedbackForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        setLoading(feedbackBtn, true);
        feedbackResult.classList.add("hidden");
        const payload = {
            prediction_id: $("#f-pred-id").value.trim(),
            machine_id: $("#f-machine-id").value.trim(),
            tenant_id: $("#f-tenant-id").value.trim(),
            actual_failure_occurred: $("#f-failure").value === "true",
            actual_failure_cause: $("#f-cause").value || null,
            actual_rul_hours: $("#f-rul").value ? parseFloat($("#f-rul").value) : null,
            operator_notes: $("#f-notes").value.trim() || null,
        };
        try {
            const data = await apiFetch("/feedback", { method: "POST", body: JSON.stringify(payload) });
            feedbackResult.classList.remove("hidden");
            feedbackResult.innerHTML = `<div class="feedback-success"><h4>✓ Feedback Submitted</h4><p>${data.message}</p><p class="mono" style="margin-top:8px">ID: ${data.feedback_id}</p></div>`;
            toast("Feedback recorded", "success");
        } catch (err) { toast(err.message, "error"); }
        finally { setLoading(feedbackBtn, false); }
    });

    // ═══════════════════════════════════════════════════════════════════════
    //  MODEL QUALITY TAB
    // ═══════════════════════════════════════════════════════════════════════

    const qualityBtn    = $("#quality-btn");
    const qualityResult = $("#quality-result");

    qualityBtn.addEventListener("click", async () => {
        setLoading(qualityBtn, true);
        qualityResult.classList.add("hidden");
        const tenant = $("#q-tenant").value.trim();
        const query = tenant ? `?tenant_id=${encodeURIComponent(tenant)}` : "";
        try {
            const data = await apiFetch(`/model_quality${query}`);
            renderQuality(data);
        } catch (err) { toast(err.message, "error"); }
        finally { setLoading(qualityBtn, false); }
    });

    function renderQuality(data) {
        qualityResult.classList.remove("hidden");
        const pct = (v) => v !== null && v !== undefined ? (v * 100).toFixed(1) + "%" : "N/A";
        let html = "";
        if (data.drift_detected) {
            html += `<div class="drift-banner warning">⚠️ ${data.drift_message}</div>`;
        } else {
            html += `<div class="drift-banner ok">✓ No concept drift detected. Model performing within acceptable thresholds.</div>`;
        }
        html += `<div class="quality-grid">
            <div class="metric-card"><div class="metric-value">${data.total_feedback}</div><div class="metric-label">Total Feedback</div></div>
            <div class="metric-card"><div class="metric-value">${pct(data.accuracy)}</div><div class="metric-label">Accuracy</div></div>
            <div class="metric-card"><div class="metric-value">${pct(data.precision)}</div><div class="metric-label">Precision</div></div>
            <div class="metric-card"><div class="metric-value">${pct(data.recall)}</div><div class="metric-label">Recall</div></div>
            <div class="metric-card"><div class="metric-value">${data.mean_rul_error_hours !== null ? data.mean_rul_error_hours + "h" : "N/A"}</div><div class="metric-label">Mean RUL Error</div></div>
        </div>`;
        const tenants = Object.entries(data.feedback_by_tenant || {});
        if (tenants.length) {
            html += `<div class="card glass"><h3 style="margin-bottom:12px">Feedback by Tenant</h3><table class="tenant-table">
                <thead><tr><th>Tenant ID</th><th>Count</th></tr></thead><tbody>`;
            tenants.forEach(([tid, count]) => {
                html += `<tr><td style="font-family:var(--font-mono)">${tid}</td><td>${count}</td></tr>`;
            });
            html += `</tbody></table></div>`;
        }
        qualityResult.innerHTML = html;
        toast("Metrics refreshed", "info");
    }
})();
