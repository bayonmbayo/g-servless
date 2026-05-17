/**
 * k6 Load Profile — STEADY LOAD
 * Constant traffic that should keep instances warm.
 * Expected effect: very few cold starts; establishes the warm baseline.
 */

import { check, sleep } from 'k6';
import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';

const coldStartCount = new Counter('cold_start_count');
const coldStartTime = new Trend('cold_start_duration_ms');
const warmStartTime = new Trend('warm_start_duration_ms');
const coldStartRate = new Rate('cold_start_rate');

export const options = {
  stages: [
    { duration: '1m', target: 10 }, // ramp up gently
    { duration: '5m', target: 10 }, // hold steady — instances should stay warm
    { duration: '30s', target: 0 }, // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // warm requests should be fast
    cold_start_rate: ['rate<0.05'],  // expect <5 % cold starts under steady load
  },
};

const BASE_URL = __ENV.FUNCTION_URL || 'https://REPLACE_WITH_YOUR_FUNCTION_URL';

export default function () {
  // Alternate between routes to exercise all code paths
  const routes = ['/health', '/data', '/cache'];
  const route = routes[Math.floor(Math.random() * routes.length)];

  const res = http.get(`${BASE_URL}${route}`, {
    tags: { profile: 'steady', route },
  });

  check(res, { 'status 200': (r) => r.status === 200 });

  if (res.status === 200) {
    const body = res.json();
    const duration = res.timings.duration;
    const cold = !!body.cold;

    coldStartRate.add(cold);
    if (cold) {
      coldStartCount.add(1);
      coldStartTime.add(duration);
    } else {
      warmStartTime.add(duration);
    }
  }

  sleep(1);
}
