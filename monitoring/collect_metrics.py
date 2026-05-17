"""
TASK OWNER: Bayon Mbayo Musewa
Metrics collection — pulls data from Google Cloud Monitoring.

Confirmed working metrics (from diagnose_metrics.py):
  ✓ run.googleapis.com/request_latencies          → latency in ms  (2nd gen)
  ✓ run.googleapis.com/request_count              → request count
  ✓ cloudfunctions.googleapis.com/function/execution_times   → latency in ns (÷1e6 → ms)
  ✓ cloudfunctions.googleapis.com/function/instance_count    → active instances
  ✓ cloudfunctions.googleapis.com/function/active_instances  → active instances

Usage:
  python collect_metrics.py --project g-servless --profile spike --runtime nodejs --hours 3
"""

import argparse
import csv
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
from google.cloud import monitoring_v3

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--project', required=True, help='GCP project ID')
parser.add_argument('--profile', required=True,
                    choices=['cold', 'burst', 'steady', 'spike'],
                    help='Load profile name')
parser.add_argument('--runtime', default='nodejs', choices=['nodejs', 'python'])
parser.add_argument('--hours',   type=float, default=3.0,
                    help='Look-back window in hours (default: 3)')
args = parser.parse_args()

client  = monitoring_v3.MetricServiceClient()
project = f'projects/{args.project}'

now   = datetime.now(tz=timezone.utc)
start = now - timedelta(hours=args.hours)

interval = monitoring_v3.TimeInterval(
    end_time   = {'seconds': int(now.timestamp())},
    start_time = {'seconds': int(start.timestamp())},
)


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch(metric_type: str, aligner):
    try:
        results = client.list_time_series(
            request={
                'name':     project,
                'filter':   f'metric.type="{metric_type}"',
                'interval': interval,
                'aggregation': monitoring_v3.Aggregation(
                    alignment_period   = {'seconds': 60},
                    per_series_aligner = aligner,
                ),
                'view': monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
            }
        )
        return list(results)
    except Exception as e:
        print(f'  Warning: could not fetch {metric_type}: {e}')
        return []


# ── Extract values from time series ──────────────────────────────────────────
def extract(series_list, unit_divisor=1.0):
    """
    Pull numeric values from a list of TimeSeries.
    unit_divisor: use 1e6 to convert nanoseconds → milliseconds.
    """
    values = []
    for series in series_list:
        for point in series.points:
            v = point.value
            raw = None
            if v.distribution_value.count > 0:
                raw = v.distribution_value.mean
            elif v.double_value != 0.0:
                raw = v.double_value
            elif v.int64_value != 0:
                raw = float(v.int64_value)
            if raw is not None:
                values.append(raw / unit_divisor)
    return values


# ── Summarise ─────────────────────────────────────────────────────────────────
def summarise(values, label: str) -> dict:
    arr = np.array(values, dtype=float)
    if len(arr) == 0:
        return {'label': label, 'count': 0,
                'mean': None, 'p50': None, 'p95': None,
                'p99': None, 'max': None, 'std': None}
    return {
        'label': label,
        'count': len(arr),
        'mean':  round(float(np.mean(arr)),           2),
        'p50':   round(float(np.percentile(arr, 50)), 2),
        'p95':   round(float(np.percentile(arr, 95)), 2),
        'p99':   round(float(np.percentile(arr, 99)), 2),
        'max':   round(float(np.max(arr)),            2),
        'std':   round(float(np.std(arr)),            2),
    }


# ── Save ──────────────────────────────────────────────────────────────────────
def save_csv(summary: dict, filename: str):
    os.makedirs('../results', exist_ok=True)
    path = f'../results/{filename}'
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=summary.keys())
        writer.writeheader()
        writer.writerow(summary)
    print(f'  Saved -> {path}')


def save_json(data, filename: str):
    os.makedirs('../results', exist_ok=True)
    path = f'../results/{filename}'
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'  Saved -> {path}')


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    tag = f'{args.profile}_{args.runtime}'
    A   = monitoring_v3.Aggregation.Aligner

    print(f'\nFetching metrics  profile={args.profile}  runtime={args.runtime}  window={args.hours}h\n')

    # ── 1. Request latency (Cloud Run / 2nd gen) ──────────────────────────────
    print('Fetching request_latencies (run.googleapis.com)...')
    latency_series  = fetch('run.googleapis.com/request_latencies', A.ALIGN_PERCENTILE_99)
    latency_values  = extract(latency_series)           # already in ms
    latency_summary = summarise(latency_values, label=f'request_latency_ms_{tag}')
    print(f'  -> {latency_summary["count"]} points  mean={latency_summary["mean"]} ms')

    # ── 2. Execution times (Cloud Functions — nanoseconds → ms) ───────────────
    print('Fetching execution_times (cloudfunctions.googleapis.com)...')
    exec_series  = fetch('cloudfunctions.googleapis.com/function/execution_times', A.ALIGN_PERCENTILE_99)
    exec_values  = extract(exec_series, unit_divisor=1_000_000)  # ns → ms
    exec_summary = summarise(exec_values, label=f'execution_times_ms_{tag}')
    print(f'  -> {exec_summary["count"]} points  mean={exec_summary["mean"]} ms')

    # ── 3. Instance count ──────────────────────────────────────────────────────
    print('Fetching instance_count (cloudfunctions.googleapis.com)...')
    inst_series  = fetch('cloudfunctions.googleapis.com/function/instance_count', A.ALIGN_MEAN)
    inst_values  = extract(inst_series)
    inst_summary = summarise(inst_values, label=f'instance_count_{tag}')
    print(f'  -> {inst_summary["count"]} points  mean={inst_summary["mean"]} instances')

    # ── 4. Active instances ────────────────────────────────────────────────────
    print('Fetching active_instances (cloudfunctions.googleapis.com)...')
    active_series  = fetch('cloudfunctions.googleapis.com/function/active_instances', A.ALIGN_MEAN)
    active_values  = extract(active_series)
    active_summary = summarise(active_values, label=f'active_instances_{tag}')
    print(f'  -> {active_summary["count"]} points  mean={active_summary["mean"]} instances')

    # ── Print summary ──────────────────────────────────────────────────────────
    result = {
        'request_latency':  latency_summary,
        'execution_times':  exec_summary,
        'instance_count':   inst_summary,
        'active_instances': active_summary,
    }
    print('\n── Results ──────────────────────────────────────────────────────────')
    print(json.dumps(result, indent=2))

    # ── Save ──────────────────────────────────────────────────────────────────
    print('\n── Saving ───────────────────────────────────────────────────────────')
    save_csv(latency_summary,  f'latency_{tag}.csv')
    save_csv(exec_summary,     f'execution_{tag}.csv')
    save_csv(inst_summary,     f'instances_{tag}.csv')
    save_csv(active_summary,   f'active_instances_{tag}.csv')
    save_json(result,          f'summary_{tag}.json')