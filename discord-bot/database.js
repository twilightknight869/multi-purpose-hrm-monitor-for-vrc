const Database = require('better-sqlite3');
const path = require('path');
const crypto = require('crypto');

const db = new Database(path.join(__dirname, 'licenses.db'));

// Create tables
db.exec(`
  CREATE TABLE IF NOT EXISTS licenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    UNIQUE NOT NULL,
    discord_id  TEXT    NOT NULL,
    discord_tag TEXT    NOT NULL,
    tier        TEXT    NOT NULL DEFAULT 'premium',
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER,          -- NULL = never expires
    active      INTEGER NOT NULL DEFAULT 1,
    note        TEXT
  );

  CREATE TABLE IF NOT EXISTS verifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT    NOT NULL,
    ip         TEXT,
    checked_at INTEGER NOT NULL
  );
`);

// ── Key generation ────────────────────────────────────────────────
function generateKey() {
  const seg = () => crypto.randomBytes(3).toString('hex').toUpperCase();
  return `HRM-${seg()}-${seg()}-${seg()}`;
}

// ── CRUD ──────────────────────────────────────────────────────────
function createKey(discordId, discordTag, note = null, expiresInDays = null) {
  const key = generateKey();
  const now = Date.now();
  const expiresAt = expiresInDays ? now + expiresInDays * 86400000 : null;

  db.prepare(`
    INSERT INTO licenses (key, discord_id, discord_tag, tier, created_at, expires_at, active, note)
    VALUES (?, ?, ?, 'premium', ?, ?, 1, ?)
  `).run(key, discordId, discordTag, now, expiresAt, note);

  return key;
}

function getKeyByDiscordId(discordId) {
  return db.prepare('SELECT * FROM licenses WHERE discord_id = ? AND active = 1').get(discordId);
}

function getKeyByKey(key) {
  return db.prepare('SELECT * FROM licenses WHERE key = ?').get(key);
}

function revokeKey(discordId) {
  const result = db.prepare('UPDATE licenses SET active = 0 WHERE discord_id = ? AND active = 1').run(discordId);
  return result.changes > 0;
}

function listKeys(limit = 20) {
  return db.prepare('SELECT * FROM licenses ORDER BY created_at DESC LIMIT ?').all(limit);
}

function verifyKey(key, ip = null) {
  const license = getKeyByKey(key);
  if (!license) return { valid: false, reason: 'unknown_key' };
  if (!license.active) return { valid: false, reason: 'revoked' };
  if (license.expires_at && Date.now() > license.expires_at)
    return { valid: false, reason: 'expired' };

  // Log the verification
  db.prepare('INSERT INTO verifications (key, ip, checked_at) VALUES (?, ?, ?)')
    .run(key, ip, Date.now());

  return {
    valid: true,
    tier: license.tier,
    discord_id: license.discord_id,
    discord_tag: license.discord_tag,
    expires_at: license.expires_at,
  };
}

function getStats() {
  return {
    total:  db.prepare('SELECT COUNT(*) as c FROM licenses').get().c,
    active: db.prepare('SELECT COUNT(*) as c FROM licenses WHERE active = 1').get().c,
    checks: db.prepare('SELECT COUNT(*) as c FROM verifications').get().c,
  };
}

module.exports = { createKey, getKeyByDiscordId, getKeyByKey, revokeKey, listKeys, verifyKey, getStats };
