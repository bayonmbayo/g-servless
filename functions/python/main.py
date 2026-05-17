"""
Google Cloud Function — Python variant
Mirrors the Node.js function so results are directly comparable.
"""

import os
import time
import json
import redis
import functions_framework
from google.cloud import firestore

# ── Module-level initialisation (cold start cost) ────────────────────────────
_COLD_START_MS = int(time.time() * 1000)
_db = firestore.Client()
_redis_client = None
_is_warm = False


def _get_redis():
    """Lazy Redis connection — created once per instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    return _redis_client


@functions_framework.http
def handler(request):
    """HTTP entry point registered with Cloud Functions."""
    global _is_warm

    handler_start = int(time.time() * 1000)
    was_cold = not _is_warm
    _is_warm = True

    path = request.path or "/"

    # ── Health check ─────────────────────────────────────────────────────────
    if path == "/health":
        return json.dumps({
            "status": "ok",
            "runtime": "python",
            "cold": was_cold,
            "uptime": int(time.time() * 1000) - _COLD_START_MS,
        }), 200, {"Content-Type": "application/json"}

    # ── Firestore read/write ──────────────────────────────────────────────────
    if path == "/data":
        fs_start = int(time.time() * 1000)
        doc_ref = _db.collection("perf-test").document("sample")
        doc_ref.set({"ts": int(time.time() * 1000), "runtime": "python"})
        doc = doc_ref.get()
        fs_latency = int(time.time() * 1000) - fs_start

        return json.dumps({
            "runtime": "python",
            "cold": was_cold,
            "firestoreLatencyMs": fs_latency,
            "data": doc.to_dict(),
        }), 200, {"Content-Type": "application/json"}

    # ── Redis cache ───────────────────────────────────────────────────────────
    if path == "/cache":
        rc = _get_redis()
        cache_start = int(time.time() * 1000)
        rc.setex("perf-key", 60, json.dumps({"ts": int(time.time() * 1000)}))
        cached = rc.get("perf-key")
        cache_latency = int(time.time() * 1000) - cache_start

        return json.dumps({
            "runtime": "python",
            "cold": was_cold,
            "redisLatencyMs": cache_latency,
            "cached": json.loads(cached),
        }), 200, {"Content-Type": "application/json"}

    # ── Default ───────────────────────────────────────────────────────────────
    return json.dumps({
        "runtime": "python",
        "cold": was_cold,
        "coldStartAge": int(time.time() * 1000) - _COLD_START_MS,
        "handlerDurationMs": int(time.time() * 1000) - handler_start,
    }), 200, {"Content-Type": "application/json"}
