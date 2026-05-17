# Pure Serverless Application Performance Analysis
**LCSS Lab Course · TH Köln · 2026 — Team 10**

> Measuring cold start effects in Google Cloud Functions across load profiles and runtimes.

---

## Task Division

| # | File(s) | Responsability |
|---|---------|-------|
| 1 | `functions/nodejs/` · `functions/python/` | **Mohamed Condé** |
| 2 | `load-tests/*.js` | **Md Abid Hossain** |
| 3 | `monitoring/collect_metrics.py` · `monitoring/analyze.py` | **Bayon Mbayo Musewa** |

---

## Project Structure

```
project/
├── functions/
│   ├── nodejs/
│   │   ├── index.js          # Cloud Function — Node.js 20
│   │   └── package.json
│   └── python/
│       ├── main.py           # Cloud Function — Python 3.11
│       └── requirements.txt
├── load-tests/
│   ├── cold-request.js       # Single isolated cold request
│   ├── burst-load.js         # Repeated bursts with idle gaps
│   ├── steady-load.js        # Constant low traffic
│   └── spike-load.js         # Sudden surge to peak
├── monitoring/
│   ├── collect_metrics.py    # Pull from Cloud Monitoring → CSV
│   └── analyze.py            # Generate charts for IEEE report
└── README.md
```

---

## 1. Cloud Functions

**Goal**: Build and deploy two functionally identical REST APIs (Node.js and Python) that expose cold/warm metadata in every response.

### Routes
| Route | Description |
|-------|-------------|
| `GET /health` | Returns `{ cold, runtime, uptime }` |
| `GET /data`   | Firestore read/write + latency |
| `GET /cache`  | Redis read/write + latency |

### Deploy (Node.js)
```bash
gcloud functions deploy lcss-nodejs \
  --gen2 \
  --runtime nodejs20 \
  --trigger-http \
  --allow-unauthenticated \
  --source functions/nodejs \
  --entry-point handler \
  --set-env-vars REDIS_URL=redis://...
```

### Deploy (Python)
```bash
gcloud functions deploy lcss-python \
  --gen2 \
  --runtime python311 \
  --trigger-http \
  --allow-unauthenticated \
  --source functions/python \
  --entry-point handler \
  --set-env-vars REDIS_URL=redis://...
```

---

## 2. Load Testing

**Goal**: Design and run all four k6 load profiles, export JSON summaries.

### Run a profile
```bash
# Set your deployed function URL
export FUNCTION_URL=https://europe-west1-YOUR_PROJECT.cloudfunctions.net/lcss-nodejs

# Cold request (run after ≥15 min idle)
k6 run load-tests/cold-request.js -e FUNCTION_URL=$FUNCTION_URL

# Steady load
k6 run load-tests/steady-load.js  -e FUNCTION_URL=$FUNCTION_URL \
   --out json=results/steady_nodejs.json

# Spike load
k6 run load-tests/spike-load.js   -e FUNCTION_URL=$FUNCTION_URL \
   --out json=results/spike_nodejs.json

# Burst load
k6 run load-tests/burst-load.js   -e FUNCTION_URL=$FUNCTION_URL \
   --out json=results/burst_nodejs.json
```
Repeat for the Python function URL.

### Key custom metrics
- `cold_start_count` — total cold starts detected
- `cold_start_duration_ms` — latency of cold requests
- `warm_start_duration_ms` — latency of warm requests

---

## 3. Monitoring & Analysis

**Goal**: Collect Cloud Monitoring metrics after each run, produce charts for the report.

### Collect metrics
```bash
pip install google-cloud-monitoring numpy matplotlib pandas

python monitoring/collect_metrics.py \
  --project YOUR_GCP_PROJECT \
  --profile spike \
  --runtime nodejs \
  --hours 1

# Repeat for all profile × runtime combinations
```

### Generate charts
```bash
python monitoring/analyze.py
# → figures/mean_exec_time.pdf
# → figures/latency_spread.pdf
# → figures/cold_start_ratio.pdf
```

### Metrics collected
| Metric | Description |
|--------|-------------|
| `function/execution_times` | Full distribution of execution durations |
| `function/instance_count` | Number of active instances (scaling events) |

---

## Research Questions (from pitch)

1. How do spike / steady / burst load profiles affect cold start frequency?
2. Is there a measurable latency difference between Node.js and Python?
3. Can periodic warm-up pings meaningfully reduce cold start overhead?

---

## Tech Stack
- **Compute**: Google Cloud Functions (2nd gen)
- **Database**: Firestore
- **Cache**: Redis (Memorystore)
- **Load testing**: k6
- **Observability**: Cloud Monitoring + Cloud Logging
- **Report**: IEEE LaTeX template
