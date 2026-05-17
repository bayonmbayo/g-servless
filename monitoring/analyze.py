"""
Analysis & Visualisation — reads real k6 --out json files.

Folder layout (relative to this script in monitoring/):
  results/        ← Node.js  k6 results  (burst_nodejs.json, spike_nodejs.json, steady_nodejs.json)
  ../results-p/   ← Python   k6 results  (same filenames)

Usage:
  python analyze.py               # real data if found, else sample
  python analyze.py --sample      # force sample/placeholder data
"""

import argparse
import json
import os
import glob
import numpy as np
import matplotlib
matplotlib.use('Agg')               # no display needed — saves to file
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--sample', action='store_true',
                    help='Use placeholder data instead of real results')
args = parser.parse_args()

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
NODEJS_DIR  = os.path.join(SCRIPT_DIR, '..', 'results')     # root/results/
PYTHON_DIR  = os.path.join(SCRIPT_DIR, '..', 'results-p')   # root/results-p/
FIGURES_DIR = os.path.join(SCRIPT_DIR, 'figures')
os.makedirs(FIGURES_DIR, exist_ok=True)

RUNTIMES = ['nodejs', 'python']
PALETTE  = {'nodejs': '#3c873a', 'python': '#3572A5'}
TRACKED  = ['http_req_duration', 'cold_start_duration_ms', 'warm_start_duration_ms']

# ── Sample placeholder data (real nodejs values + estimated python) ───────────
SAMPLE_RECORDS = [
    {'profile': 'burst',  'runtime': 'nodejs', 'total_requests': 11376, 'cold_starts': 35,
     'http_mean': 64.7,   'http_p50': 38.2,   'http_p95': 181.7,   'http_p99': 293.3,  'http_max': 602.9,
     'cold_mean': 125.3,  'cold_p50': 106.6,  'cold_p95': 259.0,   'cold_p99': 429.4,  'cold_max': 516.3,
     'warm_mean': 64.6,   'warm_p50': 38.1,   'warm_p95': 181.5,   'warm_p99': 292.2,  'warm_max': 602.9},
    {'profile': 'spike',  'runtime': 'nodejs', 'total_requests': 13296, 'cold_starts': 4,
     'http_mean': 33.0,   'http_p50': 30.3,   'http_p95': 45.8,    'http_p99': 82.9,   'http_max': 442.8,
     'cold_mean': 108.2,  'cold_p50': 71.4,   'cold_p95': 223.2,   'cold_p99': 243.6,  'cold_max': 248.7,
     'warm_mean': 33.0,   'warm_p50': 30.3,   'warm_p95': 45.7,    'warm_p99': 82.5,   'warm_max': 442.8},
    {'profile': 'steady', 'runtime': 'nodejs', 'total_requests': 332,   'cold_starts': 11,
     'http_mean': 9804.7, 'http_p50': 149.4,  'http_p95': 30034.8, 'http_p99': 30091.6,'http_max': 30185.8,
     'cold_mean': 1177.3, 'cold_p50': 1192.4, 'cold_p95': 2200.6,  'cold_p99': 2229.5, 'cold_max': 2236.8,
     'warm_mean': 232.4,  'warm_p50': 88.4,   'warm_p95': 267.9,   'warm_p99': 5331.9, 'warm_max': 5982.4},
    {'profile': 'burst',  'runtime': 'python', 'total_requests': 11000, 'cold_starts': 40,
     'http_mean': 72.0,   'http_p50': 42.0,   'http_p95': 200.0,   'http_p99': 320.0,  'http_max': 650.0,
     'cold_mean': 145.0,  'cold_p50': 120.0,  'cold_p95': 290.0,   'cold_p99': 460.0,  'cold_max': 550.0,
     'warm_mean': 71.0,   'warm_p50': 41.0,   'warm_p95': 199.0,   'warm_p99': 318.0,  'warm_max': 648.0},
    {'profile': 'spike',  'runtime': 'python', 'total_requests': 13000, 'cold_starts': 6,
     'http_mean': 38.0,   'http_p50': 34.0,   'http_p95': 52.0,    'http_p99': 95.0,   'http_max': 480.0,
     'cold_mean': 130.0,  'cold_p50': 90.0,   'cold_p95': 260.0,   'cold_p99': 280.0,  'cold_max': 290.0,
     'warm_mean': 37.0,   'warm_p50': 33.0,   'warm_p95': 51.0,    'warm_p99': 94.0,   'warm_max': 479.0},
    {'profile': 'steady', 'runtime': 'python', 'total_requests': 320,   'cold_starts': 14,
     'http_mean': 10200.0,'http_p50': 160.0,  'http_p95': 30050.0, 'http_p99': 30100.0,'http_max': 30200.0,
     'cold_mean': 1400.0, 'cold_p50': 1350.0, 'cold_p95': 2400.0,  'cold_p99': 2450.0, 'cold_max': 2500.0,
     'warm_mean': 260.0,  'warm_p50': 95.0,   'warm_p95': 290.0,   'warm_p99': 5400.0, 'warm_max': 6000.0},
]


# ── k6 JSON parser ────────────────────────────────────────────────────────────
def parse_k6_file(filepath):
    data       = {m: [] for m in TRACKED}
    cold_count = 0.0
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get('type') != 'Point':
                continue
            metric = obj.get('metric', '')
            value  = obj.get('data', {}).get('value')
            if value is None:
                continue
            if metric in data:
                data[metric].append(float(value))
            elif metric == 'cold_start_count':
                cold_count += float(value)
    return data, int(cold_count)


def summarise(data, cold_count, profile, runtime):
    def stats(arr):
        if len(arr) == 0:
            return dict(mean=0, p50=0, p95=0, p99=0, max=0)
        return dict(
            mean=round(float(np.mean(arr)),           2),
            p50 =round(float(np.percentile(arr, 50)), 2),
            p95 =round(float(np.percentile(arr, 95)), 2),
            p99 =round(float(np.percentile(arr, 99)), 2),
            max =round(float(np.max(arr)),            2),
        )
    http = stats(np.array(data['http_req_duration']))
    cold = stats(np.array(data['cold_start_duration_ms']))
    warm = stats(np.array(data['warm_start_duration_ms']))
    return {
        'profile': profile, 'runtime': runtime,
        'total_requests': len(data['http_req_duration']),
        'cold_starts':    cold_count,
        'http_mean': http['mean'], 'http_p50': http['p50'],
        'http_p95':  http['p95'],  'http_p99': http['p99'], 'http_max': http['max'],
        'cold_mean': cold['mean'], 'cold_p50': cold['p50'],
        'cold_p95':  cold['p95'],  'cold_p99': cold['p99'], 'cold_max': cold['max'],
        'warm_mean': warm['mean'], 'warm_p50': warm['p50'],
        'warm_p95':  warm['p95'],  'warm_p99': warm['p99'], 'warm_max': warm['max'],
    }


# ── Load data ─────────────────────────────────────────────────────────────────
DIR_MAP = {'nodejs': NODEJS_DIR, 'python': PYTHON_DIR}
records = []
found   = False

if not args.sample:
    for runtime, folder in DIR_MAP.items():
        for filepath in sorted(glob.glob(os.path.join(folder, '*.json'))):
            filename = os.path.basename(filepath)
            profile  = filename.split('_')[0]
            print(f'  Parsing {runtime:7s} | {profile:8s} | {filepath}')
            try:
                data, cold_count = parse_k6_file(filepath)
                rec = summarise(data, cold_count, profile, runtime)
                records.append(rec)
                found = True
                print(f'    → {rec["total_requests"]} requests, {rec["cold_starts"]} cold starts')
            except Exception as e:
                print(f'    Error: {e}')

if not found:
    print('\nNo valid data found — using sample placeholder data.\n')
    records = SAMPLE_RECORDS
else:
    print(f'\nLoaded {len(records)} file(s).\n')

df       = pd.DataFrame(records)
PROFILES = sorted(df['profile'].unique().tolist())
print(f'Profiles : {PROFILES}')
print(f'Runtimes : {df["runtime"].unique().tolist()}\n')


# ── Helper ────────────────────────────────────────────────────────────────────
def val(runtime, profile, col):
    mask = (df['runtime'] == runtime) & (df['profile'] == profile)
    rows = df[mask]
    return float(rows[col].iloc[0]) if not rows.empty else 0.0


# ── Chart 1: Cold start count ─────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
x, width = np.arange(len(PROFILES)), 0.35
for i, rt in enumerate(RUNTIMES):
    values = [val(rt, p, 'cold_starts') for p in PROFILES]
    bars   = ax.bar(x + i * width, values, width, label=rt, color=PALETTE[rt], alpha=0.85)
    for bar, v in zip(bars, values):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    str(int(v)), ha='center', va='bottom', fontsize=9)
ax.set_xticks(x + width / 2)
ax.set_xticklabels([p.upper() for p in PROFILES])
ax.set_ylabel('Cold Start Count')
ax.set_title('Number of Cold Starts per Load Profile')
ax.legend()
plt.tight_layout()
out = os.path.join(FIGURES_DIR, 'cold_start_count.pdf')
fig.savefig(out, dpi=150); print(f'Saved -> {out}'); plt.close(fig)


# ── Chart 2: Cold vs warm latency ─────────────────────────────────────────────
fig, axes = plt.subplots(1, len(PROFILES), figsize=(4 * len(PROFILES), 4), sharey=False)
if len(PROFILES) == 1:
    axes = [axes]
for ax, profile in zip(axes, PROFILES):
    categories = ['Cold P50', 'Cold P95', 'Warm P50', 'Warm P95']
    x2 = np.arange(len(categories))
    for i, rt in enumerate(RUNTIMES):
        values = [val(rt, profile, 'cold_p50'), val(rt, profile, 'cold_p95'),
                  val(rt, profile, 'warm_p50'), val(rt, profile, 'warm_p95')]
        ax.bar(x2 + i * 0.35, values, 0.35, label=rt, color=PALETTE[rt], alpha=0.85)
    ax.set_xticks(x2 + 0.175)
    ax.set_xticklabels(categories, rotation=20, ha='right', fontsize=8)
    ax.set_title(profile.upper())
    ax.set_ylabel('Latency (ms)')
    ax.legend(fontsize=8)
plt.suptitle('Cold vs Warm Latency — P50 and P95', fontsize=12)
plt.tight_layout()
out = os.path.join(FIGURES_DIR, 'cold_vs_warm_latency.pdf')
fig.savefig(out, dpi=150); print(f'Saved -> {out}'); plt.close(fig)


# ── Chart 3: Mean http_req_duration ───────────────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4))
x, width = np.arange(len(PROFILES)), 0.35
for i, rt in enumerate(RUNTIMES):
    values = [val(rt, p, 'http_mean') for p in PROFILES]
    ax.bar(x + i * width, values, width, label=rt, color=PALETTE[rt], alpha=0.85)
ax.set_xticks(x + width / 2)
ax.set_xticklabels([p.upper() for p in PROFILES])
ax.set_ylabel('Mean Response Time (ms)')
ax.set_title('Mean HTTP Request Duration by Load Profile and Runtime')
ax.legend()
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'{v:.0f} ms'))
plt.tight_layout()
out = os.path.join(FIGURES_DIR, 'mean_exec_time.pdf')
fig.savefig(out, dpi=150); print(f'Saved -> {out}'); plt.close(fig)


# ── Chart 4: Cold-start overhead ratio ────────────────────────────────────────
fig, ax = plt.subplots(figsize=(6, 4))
x, width = np.arange(len(PROFILES)), 0.35
for i, rt in enumerate(RUNTIMES):
    ratios = []
    for p in PROFILES:
        c = val(rt, p, 'cold_mean')
        w = val(rt, p, 'warm_mean')
        ratios.append(round(c / w, 2) if w > 0 else 0)
    bars = ax.bar(x + i * width, ratios, width, label=rt, color=PALETTE[rt], alpha=0.85)
    for bar, r in zip(bars, ratios):
        if r > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                    f'{r:.1f}x', ha='center', va='bottom', fontsize=9)
ax.set_xticks(x + width / 2)
ax.set_xticklabels([p.upper() for p in PROFILES])
ax.set_ylabel('Cold / Warm Latency Ratio')
ax.set_title('Cold-Start Overhead Ratio (cold mean / warm mean)')
ax.axhline(y=1, linestyle='--', color='grey', linewidth=0.8, label='1x baseline')
ax.legend()
plt.tight_layout()
out = os.path.join(FIGURES_DIR, 'cold_start_ratio.pdf')
fig.savefig(out, dpi=150); print(f'Saved -> {out}'); plt.close(fig)


# ── Summary table ─────────────────────────────────────────────────────────────
print('\n── Summary ───────────────────────────────────────────────────────────')
print(f'{"Profile":<10} {"Runtime":<10} {"Requests":>10} {"Cold#":>7} '
      f'{"http_mean":>10} {"http_p95":>10} {"cold_mean":>10} {"warm_mean":>10}')
print('-' * 80)
for _, row in df.sort_values(['profile', 'runtime']).iterrows():
    print(f'{row["profile"]:<10} {row["runtime"]:<10} {int(row["total_requests"]):>10} '
          f'{int(row["cold_starts"]):>7} {row["http_mean"]:>10.1f} {row["http_p95"]:>10.1f} '
          f'{row["cold_mean"]:>10.1f} {row["warm_mean"]:>10.1f}')

print(f'\nAll charts saved to {FIGURES_DIR}')