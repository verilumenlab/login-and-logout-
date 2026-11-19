/**
 * After a new desktop version installs, clear auth so the employee must
 * sign in again with their work email (no auto-login / saved session).
 */

const fs = require('node:fs');
const path = require('node:path');
const { app, Notification } = require('electron');
const native = require('./native.cjs');

const STATE_FILE = 'app-session-state.json';

function statePath() {
  return path.join(app.getPath('userData'), STATE_FILE);
}

function readState() {
  try {
    const raw = fs.readFileSync(statePath(), 'utf8');
    return JSON.parse(raw) || {};
  } catch {
    return {};
  }
}

function writeState(state) {
  try {
    fs.writeFileSync(statePath(), JSON.stringify(state, null, 2), 'utf8');
  } catch (err) {
    console.warn('[session-reset] writeState failed:', err?.message || err);
  }
}

async function clearAuthSecrets() {
  try {
    await native.deleteSecureToken('access_token');
    await native.deleteSecureToken('refresh_token');
    await native.deleteSecureToken('saved_login');
  } catch (err) {
    console.warn('[session-reset] clearAuthSecrets failed:', err?.message || err);
  }
}

/**
 * Call right before quitAndInstall so the next launch requires email sign-in.
 */
async function prepareReloginBeforeUpdate({ fromVersion, toVersion } = {}) {
  const current = String(fromVersion || '').trim() || null;
  const next = String(toVersion || '').trim() || null;
  await clearAuthSecrets();
  writeState({
    ...readState(),
    lastVersion: current,
    requireRelogin: true,
    fromVersion: current,
    toVersion: next,
    reason: 'update',
    markedAt: new Date().toISOString(),
  });
}

/**
 * On every app start: if version changed or update flagged, wipe auth and
 * remember that the UI must show the email login screen.
 */
async function enforceReloginOnVersionChange(currentVersion) {
  const version = String(currentVersion || '').trim() || '0.0.0';
  const state = readState();
  const lastVersion = state.lastVersion ? String(state.lastVersion) : null;
  const flagged = Boolean(state.requireRelogin);
  const versionChanged = Boolean(lastVersion) && lastVersion !== version;
  const required = flagged || versionChanged;

  if (!required) {
    if (lastVersion !== version) {
      writeState({ ...state, lastVersion: version, requireRelogin: false });
    }
    return { required: false, version, fromVersion: lastVersion, toVersion: version };
  }

  await clearAuthSecrets();
  const fromVersion = state.fromVersion || lastVersion;
  writeState({
    lastVersion: version,
    requireRelogin: true,
    fromVersion,
    toVersion: state.toVersion || version,
    reason: state.reason || (versionChanged ? 'version_change' : 'update'),
    markedAt: state.markedAt || new Date().toISOString(),
  });

  try {
    if (Notification.isSupported()) {
      const note = new Notification({
        title: 'WorkPulse updated — sign in again',
        body: `Version ${version} is installed. Open WorkPulse and sign in with your work email.`,
        silent: false,
      });
      note.show();
    }
  } catch {
    // ignore
  }

  return {
    required: true,
    version,
    fromVersion,
    toVersion: state.toVersion || version,
    reason: state.reason || 'update',
  };
}

/**
 * Renderer consumes the one-shot flag after showing the login screen.
 */
function consumeReloginRequirement() {
  const state = readState();
  const required = Boolean(state.requireRelogin);
  const payload = {
    required,
    version: state.toVersion || state.lastVersion || null,
    fromVersion: state.fromVersion || null,
    toVersion: state.toVersion || state.lastVersion || null,
    reason: state.reason || null,
  };
  if (required) {
    writeState({
      lastVersion: state.lastVersion || payload.version,
      requireRelogin: false,
      fromVersion: null,
      toVersion: null,
      reason: null,
      consumedAt: new Date().toISOString(),
    });
  }
  return payload;
}

module.exports = {
  prepareReloginBeforeUpdate,
  enforceReloginOnVersionChange,
  consumeReloginRequirement,
  clearAuthSecrets,
};
