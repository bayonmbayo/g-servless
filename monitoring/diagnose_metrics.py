"""
Diagnostic script — run this to find which metrics actually exist in your project.
Usage:
  python diagnose_metrics.py --project g-servless
"""

import argparse
from datetime import datetime, timedelta, timezone
from google.cloud import monitoring_v3

parser = argparse.ArgumentParser()
parser.add_argument('--project', required=True)
parser.add_argument('--hours',   type=float, default=6.0)
args = parser.parse_args()

client  = monitoring_v3.MetricServiceClient()
project = f'projects/{args.project}'

now   = datetime.now(tz=timezone.utc)
start = now - timedelta(hours=args.hours)

interval = monitoring_v3.TimeInterval(
    end_time   = {'seconds': int(now.timestamp())},
    start_time = {'seconds': int(start.timestamp())},
)

# List of candidate metrics to probe
CANDIDATES = [
    # Cloud Run (2nd gen functions)
    ('run.googleapis.com/request_latencies',        monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_99),
    ('run.googleapis.com/request_count',            monitoring_v3.Aggregation.Aligner.ALIGN_RATE),
    ('run.googleapis.com/container/cpu/utilizations', monitoring_v3.Aggregation.Aligner.ALIGN_MEAN),
    # Cloud Functions 1st gen
    ('cloudfunctions.googleapis.com/function/execution_times',  monitoring_v3.Aggregation.Aligner.ALIGN_PERCENTILE_99),
    ('cloudfunctions.googleapis.com/function/instance_count',   monitoring_v3.Aggregation.Aligner.ALIGN_MEAN),
    ('cloudfunctions.googleapis.com/function/active_instances', monitoring_v3.Aggregation.Aligner.ALIGN_MEAN),
]

print(f'\nProject : {args.project}')
print(f'Window  : last {args.hours} hours')
print(f'Time    : {start.strftime("%H:%M")} → {now.strftime("%H:%M")} UTC\n')
print(f'{"Metric":<65} {"Points":>7}  {"Sample value"}')
print('-' * 90)

for metric_type, aligner in CANDIDATES:
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
        series_list = list(results)
        total_points = sum(len(s.points) for s in series_list)

        sample = ''
        if total_points > 0:
            p = series_list[0].points[0].value
            if p.distribution_value.count > 0:
                sample = f'mean={p.distribution_value.mean:.1f}'
            elif p.double_value:
                sample = f'{p.double_value:.2f}'
            elif p.int64_value:
                sample = str(p.int64_value)

        status = '✓' if total_points > 0 else '✗'
        print(f'{status}  {metric_type:<63} {total_points:>7}  {sample}')

    except Exception as e:
        short = str(e)[:60]
        print(f'!  {metric_type:<63} {"ERROR":>7}  {short}')

print('\nDone. Use the metrics marked ✓ in collect_metrics.py')
