/**
 * k6 Load Profile — BURST LOAD
 * Repeated short bursts with idle gaps between them.
 * Expected effect: each gap lets instances cool down → repeated cold starts.
 */

import { check, sleep } from 'k6';
import http from 'k6/http';
import { Counter, Trend } from 'k6/metrics';

const coldStartCount = new Counter('cold_start_count');
const coldStartTime = new Trend('cold_start_duration_ms');
const warmStartTime = new Trend('warm_start_duration_ms');

// Three burst waves separated by idle periods
export const options = {
  scenarios: {
    burst_1: {
      executor: 'ramping-vus',
      startTime: '0s',
      stages: [
        { duration: '10s', target: 50 },
        { duration: '20s', target: 50 },
        { duration: '5s', target: 0 },
      ],
      tags: { burst: '1' },
    },
    burst_2: {
      executor: 'ramping-vus',
      startTime: '3m', // idle gap — instances should go cold
      stages: [
        { duration: '10s', target: 50 },
        { duration: '20s', target: 50 },
        { duration: '5s', target: 0 },
      ],
      tags: { burst: '2' },
    },
    burst_3: {
      executor: 'ramping-vus',
      startTime: '6m',
      stages: [
        { duration: '10s', target: 50 },
        { duration: '20s', target: 50 },
        { duration: '5s', target: 0 },
      ],
      tags: { burst: '3' },
    },
  },
  thresholds: {
    http_req_duration: ['p(99)<3000'],
  },
};

const BASE_URL = __ENV.FUNCTION_URL || 'https://REPLACE_WITH_YOUR_FUNCTION_URL';

export default function () {
  const res = http.get(`${BASE_URL}/health`, {
    tags: { profile: 'burst' },
  });

  check(res, { 'status 200': (r) => r.status === 200 });

  if (res.status === 200) {
    const body = res.json();
    const duration = res.timings.duration;

    if (body.cold) {
      coldStartCount.add(1);
      coldStartTime.add(duration);
    } else {
      warmStartTime.add(duration);
    }
  }

  sleep(0.3);
}
