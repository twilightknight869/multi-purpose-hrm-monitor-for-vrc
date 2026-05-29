const express = require('express');
const { verifyKey, getStats } = require('./database');

const app = express();
app.use(express.json());

const API_SECRET = process.env.API_SECRET || 'change-me-in-env';

// ── Middleware: require secret header ─────────────────────────────
function requireSecret(req, res, next) {
  if (req.headers['x-hrm-secret'] !== API_SECRET) {
    console.log(`[Auth] REJECTED ${req.method} ${req.path} — bad secret`);
    return res.status(401).json({ error: 'unauthorized' });
  }
  next();
}

// ── License verification ──────────────────────────────────────────
app.get('/verify', requireSecret, (req, res) => {
  const key = req.query.key?.trim();
  if (!key) return res.status(400).json({ valid: false, reason: 'no_key' });
  const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
  res.json(verifyKey(key, ip));
});

app.get('/stats', requireSecret, (req, res) => res.json(getStats()));

// ══════════════════════════════════════════════════════════════════
//  BPM RELAY — no rate limits, no third-party service
//
//  HOST:   POST /relay/:roomcode   { bpm: 75 }   (authenticated)
//  VIEWER: GET  /relay/:roomcode/sse              (authenticated)
//
//  The server keeps the latest BPM per room in memory and pushes
//  it to all connected SSE clients whenever the host publishes.
// ══════════════════════════════════════════════════════════════════

// In-memory state: roomCode → { bpm, ts, clients: Set<res> }
const rooms = new Map();

function getRoom(code) {
  if (!rooms.has(code)) rooms.set(code, { bpm: 0, ts: 0, clients: new Set() });
  return rooms.get(code);
}

// ── HOST: publish BPM ─────────────────────────────────────────────
app.post('/relay/:code', requireSecret, (req, res) => {
  const code = req.params.code.toUpperCase().slice(0, 6);
  const bpm  = parseInt(req.body?.bpm ?? req.query.bpm ?? 0, 10);
  if (!bpm || bpm < 20 || bpm > 300)
    return res.status(400).json({ error: 'invalid bpm' });

  const room = getRoom(code);
  room.bpm = bpm;
  room.ts  = Date.now();

  // Push to all connected viewers
  const data = JSON.stringify({ bpm, ts: room.ts });
  for (const client of room.clients) {
    try { client.write(`data: ${data}\n\n`); }
    catch { room.clients.delete(client); }
  }

  console.log(`[Relay] ${code} BPM=${bpm} pushed to ${room.clients.size} viewer(s)`);
  res.json({ ok: true, viewers: room.clients.size });
});

// ── VIEWER: SSE subscribe ─────────────────────────────────────────
app.get('/relay/:code/sse', requireSecret, (req, res) => {
  const code = req.params.code.toUpperCase().slice(0, 6);
  const room = getRoom(code);

  res.setHeader('Content-Type',  'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection',    'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');   // disable Nginx buffering on Railway
  res.flushHeaders();

  // Send last known BPM immediately so viewer sees something right away
  if (room.bpm > 0)
    res.write(`data: ${JSON.stringify({ bpm: room.bpm, ts: room.ts })}\n\n`);

  // Send a keepalive comment every 25 s so Railway/Cloudflare don't time out
  const keepalive = setInterval(() => {
    try { res.write(': keepalive\n\n'); } catch { clearInterval(keepalive); }
  }, 25_000);

  room.clients.add(res);
  console.log(`[Relay] ${code} viewer connected (${room.clients.size} total)`);

  req.on('close', () => {
    clearInterval(keepalive);
    room.clients.delete(res);
    console.log(`[Relay] ${code} viewer disconnected (${room.clients.size} remaining)`);
  });
});

// ── 404 ───────────────────────────────────────────────────────────
app.use((_, res) => res.status(404).json({ error: 'not found' }));

function startApi(port = 3000) {
  app.listen(port, () => console.log(`[API] Listening on port ${port}`));
}

module.exports = { startApi };
