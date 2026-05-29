const fs   = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_FILE = path.join(__dirname, 'licenses.json');

// ── Load / save ───────────────────────────────────────────────────
function load() {
  if (!fs.existsSync(DB_FILE)) return { licenses: [], verifications: [] };
  try { return JSON.parse(fs.readFileSync(DB_FILE, 'utf8')); }
  catch { return { licenses: [], verifications: [] }; }
}

function save(data) {
  fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
}

// ── Key generation ────────────────────────────────────────────────
function generateKey() {
  const seg = () => crypto.randomBytes(3).toString('hex').toUpperCase();
  return `HRM-${seg()}-${seg()}-${seg()}`;
}

// ── CRUD ──────────────────────────────────────────────────────────
function createKey(discordId, discordTag, note = null, expiresInDays = null) {
  const db  = load();
  const key = generateKey();
  const now = Date.now();

  db.licenses.push({
    id:          db.licenses.length + 1,
    key,
    discord_id:  discordId,
    discord_tag: discordTag,
    tier:        'premium',
    created_at:  now,
    expires_at:  expiresInDays ? now + expiresInDays * 86400000 : null,
    active:      true,
    note,
  });
  save(db);
  return key;
}

function getKeyByDiscordId(discordId) {
  return load().licenses.find(k => k.discord_id === discordId && k.active) ?? null;
}

function getKeyByKey(key) {
  return load().licenses.find(k => k.key === key) ?? null;
}

function revokeKey(discordId) {
  const db = load();
  const entry = db.licenses.find(k => k.discord_id === discordId && k.active);
  if (!entry) return false;
  entry.active = false;
  save(db);
  return true;
}

function listKeys(limit = 20) {
  return load().licenses.slice(-limit).reverse();
}

function verifyKey(key, ip = null) {
  const license = getKeyByKey(key);
  if (!license)         return { valid: false, reason: 'unknown_key' };
  if (!license.active)  return { valid: false, reason: 'revoked' };
  if (license.expires_at && Date.now() > license.expires_at)
    return { valid: false, reason: 'expired' };

  // Log verification
  const db = load();
  db.verifications.push({ key, ip, checked_at: Date.now() });
  save(db);

  return {
    valid:       true,
    tier:        license.tier,
    discord_id:  license.discord_id,
    discord_tag: license.discord_tag,
    expires_at:  license.expires_at,
  };
}

function getStats() {
  const db = load();
  return {
    total:  db.licenses.length,
    active: db.licenses.filter(k => k.active).length,
    checks: db.verifications.length,
  };
}

module.exports = { createKey, getKeyByDiscordId, getKeyByKey, revokeKey, listKeys, verifyKey, getStats };
