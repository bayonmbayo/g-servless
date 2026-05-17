/**
 * TASK OWNER: Md Abid Hossain
 * k6 Load Profile — SPIKE LOAD
 * Simulates a sudden traffic surge from near-zero to peak, then back down.
 * Expected effect: forces many simultaneous cold starts.
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Trend } from 'k6/metrics';

// ── Custom metrics ────────────────────────────────────────────────────────────
const coldStartCount  = new Counter('cold_start_count');
const coldStartTime   = new Trend('cold_start_duration_ms');
const warmStartTime   = new Trend('warm_start_duration_ms');

// ── Spike profile ─────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: '30s', target: 1   }, // idle baseline
    { duration: '10s', target: 100 }, // spike up — triggers cold starts
    { duration: '1m',  target: 100 }, // sustained peak
    { duration: '10s', target: 1   }, // drop back — instances will go cold again
    { duration: '30s', target: 1   }, // observe recovery
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95th percentile under 2 s
    http_req_failed:   ['rate<0.01'],  // error rate under 1 %
  },
};

const BASE_URL = __ENV.FUNCTION_URL || 'https://REPLACE_WITH_YOUR_FUNCTION_URL';

export default function () {
  const res = http.get(`${BASE_URL}/health`, {
    tags: { profile: 'spike' },
  });

  const ok = check(res, {
    'status 200': (r) => r.status === 200,
    'has cold flag': (r) => r.json('cold') !== undefined,
  });

  if (ok) {
    const body = res.json();
    const duration = res.timings.duration;

    if (body.cold) {
      coldStartCount.add(1);
      coldStartTime.add(duration);
    } else {
      warmStartTime.add(duration);
    }
  }

  sleep(0.5);
}
