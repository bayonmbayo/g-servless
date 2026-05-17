/**
 * Google Cloud Function — Node.js variant
 * Measures cold start vs warm start latency
 */

const { Firestore } = require('@google-cloud/firestore');
const redis = require('redis');

// Module-level init — executed ONCE per instance (cold start only)
const db = new Firestore();
let redisClient = null;

const COLD_START_TIME = Date.now(); // Captured at container init
let isWarm = false;

/**
 * Lazily initialise Redis so we can measure connection cost separately.
 */
async function getRedisClient() {
  if (!redisClient) {
    redisClient = redis.createClient({ url: process.env.REDIS_URL });
    await redisClient.connect();
  }
  return redisClient;
}

/**
 * Main HTTP handler — entry point for Cloud Functions.
 * Responds with timing metadata so k6 can distinguish cold vs warm requests.
 */
exports.handler = async (req, res) => {
  const handlerStart = Date.now();
  const wasCold = !isWarm;
  isWarm = true; // mark instance as warm for subsequent requests

  try {
    const route = req.path || '/';

    // ── Route: health check ──────────────────────────────────────────────
    if (route === '/health') {
      return res.status(200).json({
        status: 'ok',
        runtime: 'nodejs',
        cold: wasCold,
        uptime: Date.now() - COLD_START_TIME,
      });
    }

    // ── Route: Firestore read/write ──────────────────────────────────────
    if (route === '/data') {
      const fsStart = Date.now();
      const docRef = db.collection('perf-test').doc('sample');
      await docRef.set({ ts: Date.now(), runtime: 'nodejs' });
      const doc = await docRef.get();
      const fsLatency = Date.now() - fsStart;

      return res.status(200).json({
        runtime: 'nodejs',
        cold: wasCold,
        firestoreLatencyMs: fsLatency,
        data: doc.data(),
      });
    }

    // ── Route: Redis cache ───────────────────────────────────────────────
    if (route === '/cache') {
      const rc = await getRedisClient();
      const cacheStart = Date.now();
      await rc.set('perf-key', JSON.stringify({ ts: Date.now() }), { EX: 60 });
      const cached = await rc.get('perf-key');
      const cacheLatency = Date.now() - cacheStart;

      return res.status(200).json({
        runtime: 'nodejs',
        cold: wasCold,
        redisLatencyMs: cacheLatency,
        cached: JSON.parse(cached),
      });
    }

    // ── Default response ─────────────────────────────────────────────────
    return res.status(200).json({
      runtime: 'nodejs',
      cold: wasCold,
      coldStartAge: Date.now() - COLD_START_TIME,
      handlerDurationMs: Date.now() - handlerStart,
    });

  } catch (err) {
    console.error('Handler error:', err);
    return res.status(500).json({ error: err.message });
  }
};
