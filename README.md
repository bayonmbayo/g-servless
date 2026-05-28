# Pure Serverless Application Performance Analysis
**LCSS Lab Course · TH Köln · 2026 — Team 10**

> Measuring cold start effects in Google Cloud Functions across load profiles and runtimes.

---

## Team & Task Division

| # | Responsability | Files |
|---|-------|-------|
| 1 | **Mohamed Condé** | `functions/nodejs/` · `functions/python/` |
| 2 | **Md Abid Hossain** | `load-tests/*.js` |
| 3 | **Bayon Mbayo Musewa** | `monitoring/collect_metrics.py` · `monitoring/analyze.py` |

---

## Project Structure

```
g-servless/
├── functions/
│   ├── nodejs/
│   │   ├── index.js              # Cloud Function — Node.js 20
│   │   └── package.json
│   └── python/
│       ├── main.py               # Cloud Function — Python 3.12
│       └── requirements.txt
├── load-tests/
│   ├── cold-request.js           # Single isolated cold request
│   ├── burst-load.js             # Repeated bursts with idle gaps
│   ├── steady-load.js            # Constant low traffic
│   └── spike-load.js             # Sudden surge to peak
├── monitoring/
│   ├── collect_metrics.py        # Pull from Cloud Monitoring → CSV/JSON
│   ├── analyze.py                # Generate charts for IEEE report
│   ├── diagnose_metrics.py       # Debug: list available GCP metrics
│   └── requirements.txt
├── results/                      # k6 output — Node.js runs
├── results-p/                    # k6 output — Python runs
└── README.md
```

---

## Prerequisites

### 1. Google Cloud SDK (gcloud)

Download and install from https://cloud.google.com/sdk/docs/install

```powershell
# Verify installation
gcloud --version

# Login with your Google account
gcloud auth login
gcloud auth application-default login   # required for Python scripts

# Set the project
gcloud config set project g-servless
```

### 2. Node.js (v20+)

Download from https://nodejs.org

```powershell
node --version    # should print v20.x.x or higher
npm --version
```

### 3. Python (3.11+)

Download from https://python.org

```powershell
python --version  # should print 3.11.x or higher
```

Install Python dependencies for monitoring scripts:

```powershell
cd monitoring
pip install -r requirements.txt
```

`requirements.txt` contains:
```
google-cloud-monitoring==2.*
numpy==2.*
matplotlib==3.*
pandas==2.*
```

### 4. k6 Load Testing Tool

```powershell
# Windows (with Chocolatey)
choco install k6 -y

# Verify
k6 version
```

If you don't have Chocolatey, download the k6 installer directly from:
https://github.com/grafana/k6/releases

---

## GCP Setup (one-time, done by project owner)

### 1. Enable required APIs

```powershell
gcloud services enable `
  cloudfunctions.googleapis.com `
  cloudbuild.googleapis.com `
  run.googleapis.com `
  firestore.googleapis.com `
  redis.googleapis.com `
  monitoring.googleapis.com
```

### 2. Create Firestore database

```powershell
gcloud firestore databases create --location=europe-west1
```

> Note: use `--location`, not `--region` (common mistake).

### 3. Create Redis instance (Memorystore)

```powershell
gcloud redis instances create lcss-redis `
  --size=1 `
  --region=europe-west1 `
  --tier=BASIC
```

Get the Redis IP address (needed for the function deploy):

```powershell
gcloud redis instances describe lcss-redis `
  --region=europe-west1 `
  --format="value(host)"
```

> Redis is only reachable from within GCP — your functions and Redis must be
> in the same project and region.

### 4. Grant team members access

The project owner must run this for each team member:

```powershell
# Replace with each member's Google account email
gcloud projects add-iam-policy-binding g-servless `
  --member="user:teammate@gmail.com" `
  --role="roles/monitoring.viewer"

# Also grant Cloud Functions invoker if needed
gcloud projects add-iam-policy-binding g-servless `
  --member="user:teammate@gmail.com" `
  --role="roles/cloudfunctions.invoker"
```

---

## 1. Deploy Cloud Functions (Mohamed)

### Node.js

```powershell
cd functions/nodejs
npm install

gcloud functions deploy lcss-nodejs `
  --gen2 `
  --runtime nodejs20 `
  --region europe-west1 `
  --trigger-http `
  --allow-unauthenticated `
  --entry-point handler `
  --source . `
  --memory 256MB `
  --timeout 30s `
  --set-env-vars REDIS_URL=redis://YOUR_REDIS_IP:6379
```

### Python

```powershell
cd functions/python

gcloud functions deploy lcss-python `
  --gen2 `
  --runtime python312 `
  --region europe-west1 `
  --trigger-http `
  --allow-unauthenticated `
  --entry-point handler `
  --source . `
  --memory 256MB `
  --timeout 30s `
  --set-env-vars REDIS_URL=redis://YOUR_REDIS_IP:6379
```

### Get function URLs

```powershell
gcloud functions describe lcss-nodejs `
  --region europe-west1 `
  --format="value(serviceConfig.uri)"

gcloud functions describe lcss-python `
  --region europe-west1 `
  --format="value(serviceConfig.uri)"
```

### Smoke test

```powershell
curl https://YOUR_NODEJS_URL/health
# Expected: {"status":"ok","runtime":"nodejs","cold":true,...}

curl https://YOUR_PYTHON_URL/health
# Expected: {"status":"ok","runtime":"python","cold":true,...}
```

### Response fields explained

| Field | Meaning |
|-------|---------|
| `cold: true` | This was a cold start (container freshly booted) |
| `cold: false` | Instance was already warm |
| `coldStartAge` | ms since the container was initialised |
| `handlerDurationMs` | Time the handler itself took (excludes boot time) |

> The total cold start penalty is measured by k6 as `res.timings.duration`,
> not by `handlerDurationMs`.

---

## 2. Load Testing (Abid)

### Setup

```powershell
# Create output folders
New-Item -ItemType Directory -Force -Path results
New-Item -ItemType Directory -Force -Path results-p

# Set function URLs
$env:NODEJS_URL = $(gcloud functions describe lcss-nodejs `
  --region europe-west1 --format="value(serviceConfig.uri)")

$env:PYTHON_URL = $(gcloud functions describe lcss-python `
  --region europe-west1 --format="value(serviceConfig.uri)")
```

### Run Node.js profiles

Always run cold request first, after ≥15 min idle:

```powershell
# 1. Cold request — wait 15+ min after last invocation
k6 run load-tests/cold-request.js -e FUNCTION_URL=$env:NODEJS_URL

# 2. Steady load
k6 run load-tests/steady-load.js `
  -e FUNCTION_URL=$env:NODEJS_URL `
  --out json=results/steady_nodejs.json

# 3. Spike load
k6 run load-tests/spike-load.js `
  -e FUNCTION_URL=$env:NODEJS_URL `
  --out json=results/spike_nodejs.json

# 4. Burst load
k6 run load-tests/burst-load.js `
  -e FUNCTION_URL=$env:NODEJS_URL `
  --out json=results/burst_nodejs.json
```

### Run Python profiles

```powershell
k6 run load-tests/cold-request.js -e FUNCTION_URL=$env:PYTHON_URL

k6 run load-tests/steady-load.js `
  -e FUNCTION_URL=$env:PYTHON_URL `
  --out json=results-p/steady_nodejs.json

k6 run load-tests/spike-load.js `
  -e FUNCTION_URL=$env:PYTHON_URL `
  --out json=results-p/spike_nodejs.json

k6 run load-tests/burst-load.js `
  -e FUNCTION_URL=$env:PYTHON_URL `
  --out json=results-p/burst_nodejs.json
```

### Key custom metrics in k6 output

| Metric | Description |
|--------|-------------|
| `cold_start_count` | Total cold starts detected |
| `cold_start_duration_ms` | Latency of cold requests |
| `warm_start_duration_ms` | Latency of warm requests |
| `http_req_duration` | Full round-trip latency (most important) |

---

## 3. Monitoring & Analysis (Bayon)

### Collect metrics from Cloud Monitoring

Run after each k6 test (while data is still within the time window):

```powershell
cd monitoring

# Collect for each profile × runtime combination
python collect_metrics.py --project g-servless --profile spike  --runtime nodejs --hours 3
python collect_metrics.py --project g-servless --profile burst  --runtime nodejs --hours 3
python collect_metrics.py --project g-servless --profile steady --runtime nodejs --hours 3
python collect_metrics.py --project g-servless --profile spike  --runtime python --hours 3
python collect_metrics.py --project g-servless --profile burst  --runtime python --hours 3
python collect_metrics.py --project g-servless --profile steady --runtime python --hours 3
```

> Tip: run collect_metrics.py **immediately after** each k6 test, before
> the data ages out of the 1-hour default window.

### Generate charts

```powershell
cd monitoring
python analyze.py
```

Produces in `monitoring/figures/`:

| File | Chart |
|------|-------|
| `cold_start_count.pdf` | Cold starts per load profile |
| `cold_vs_warm_latency.pdf` | P50 / P95 cold vs warm per profile |
| `mean_exec_time.pdf` | Mean response time by profile × runtime |
| `cold_start_ratio.pdf` | Cold ÷ warm latency overhead ratio |

### Diagnose missing metrics

If `collect_metrics.py` returns nulls, run the diagnostic first:

```powershell
python diagnose_metrics.py --project g-servless --hours 6
```

This lists every available metric with point counts so you can see
exactly what data exists in GCP.

---

## Research Questions

| # | Question |
|---|---------|
| RQ1 | How do spike / steady / burst load profiles affect cold start frequency? |
| RQ2 | Is there a measurable latency difference between Node.js and Python? |
| RQ3 | Can periodic warm-up pings meaningfully reduce cold start overhead? |

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Compute | Google Cloud Functions 2nd gen (Cloud Run) |
| Database | Firestore (`europe-west1`) |
| Cache | Redis — Memorystore Basic tier |
| Load testing | k6 |
| Observability | Cloud Monitoring + Cloud Logging |
| Analysis | Python — pandas, numpy, matplotlib |
| Report | IEEE LaTeX template |

---

## Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `--region` not recognised for Firestore | Use `--location` instead |
| `PERMISSION_DENIED` in collect_metrics.py | Run `gcloud auth application-default login` |
| `ALIGN_PERCENTILE_99` invalid for instance_count | Use `ALIGN_MEAN` for GAUGE/INT64 metrics |
| execution_times values in billions | Values are in nanoseconds — divide by 1,000,000 for ms |
| k6 `cold: false` on first request | Function was pre-warmed by GCP — wait 15+ min and retry |
| `results/` folder not found | Run `New-Item -ItemType Directory -Force -Path results` |