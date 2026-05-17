/**
 * k6 Load Profile — COLD REQUEST
 * A single request after a long idle period; guarantees a cold start.
 * Run this after waiting ≥15 min since the last invocation.
 *
 * Usage:
 *   k6 run cold-request.js -e FUNCTION_URL=https://...
 */

import { check } from 'k6';
import http from 'k6/http';

export const options = {
  vus: 1,
  iterations: 1,
};

const BASE_URL = __ENV.FUNCTION_URL || 'https://REPLACE_WITH_YOUR_FUNCTION_URL';

export default function () {
  console.log('Sending isolated cold request...');

  const res = http.get(`${BASE_URL}/health`);

  check(res, {
    'status 200': (r) => r.status === 200,
    'is cold': (r) => r.json('cold') === true,
  });

  console.log(`Cold: ${res.json('cold')} | Duration: ${res.timings.duration.toFixed(1)} ms`);
}
