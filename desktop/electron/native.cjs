/**
 * Windows native helpers for WorkPulse Employee (Electron main process).
 * All child processes use windowsHide so no CMD/PowerShell window flashes.
 */
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const os = require('node:os');
const fs = require('node:fs');
const path = require('node:path');
const { app, safeStorage } = require('electron');

const execFileAsync = promisify(execFile);

const HIDDEN = {
  windowsHide: true,
  timeout: 15000,
  maxBuffer: 2 * 1024 * 1024,
};

async function run(command, args = []) {
  try {
    const { stdout } = await execFileAsync(command, args, HIDDEN);
    return String(stdout || '');
  } catch {
    return '';
  }
}

async function runPs(script) {
  return run('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', script]);
}

function vaultDir() {
  const dir = path.join(app.getPath('userData'), 'vault');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function vaultPath(key) {
  const safe = String(key).replace(/[^a-zA-Z0-9._-]/g, '_');
  return path.join(vaultDir(), `${safe}.bin`);
}

async function saveSecureToken(key, value) {
  const file = vaultPath(key);
  if (safeStorage.isEncryptionAvailable()) {
    const encrypted = safeStorage.encryptString(String(value));
    fs.writeFileSync(file, encrypted);
  } else {
    fs.writeFileSync(file, Buffer.from(String(value), 'utf8'));
  }
}

async function getSecureToken(key) {
  const file = vaultPath(key);
  if (!fs.existsSync(file)) return null;
  const buf = fs.readFileSync(file);
  try {
    if (safeStorage.isEncryptionAvailable()) {
      return safeStorage.decryptString(buf);
    }
    return buf.toString('utf8');
  } catch {
    return null;
  }
}

async function deleteSecureToken(key) {
  const file = vaultPath(key);
  if (fs.existsSync(file)) fs.unlinkSync(file);
}

async function getHardwareUuid() {
  const out = await runPs(
    "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"
  );
  const uuid = out.trim().split(/\r?\n/).pop()?.trim();
  if (uuid && uuid.length > 8 && !/^FFFFFFFF/i.test(uuid)) return uuid;

  const fallback = path.join(vaultDir(), 'device-id.txt');
  if (fs.existsSync(fallback)) return fs.readFileSync(fallback, 'utf8').trim();
  const generated = `WP-${os.hostname()}-${Date.now().toString(36)}`.toUpperCase();
  fs.writeFileSync(fallback, generated);
  return generated;
}

async function getMacAddress() {
  const nics = os.networkInterfaces();
  for (const entries of Object.values(nics)) {
    for (const e of entries || []) {
      if (!e.internal && e.mac && e.mac !== '00:00:00:00:00:00') return e.mac;
    }
  }
  return '';
}

async function getIpAddress() {
  const nics = os.networkInterfaces();
  for (const entries of Object.values(nics)) {
    for (const e of entries || []) {
      if (!e.internal && e.family === 'IPv4') return e.address;
    }
  }
  return '';
}

async function getBattery() {
  const out = await runPs(
    `$b=Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1; if($b){"$($b.EstimatedChargeRemaining)|$($b.BatteryStatus)"}`
  );
  const line = out.trim();
  if (!line) return { battery_percent: null, is_charging: null };
  const [pct, status] = line.split('|');
  const percent = Number.parseInt(pct, 10);
  const st = Number.parseInt(status, 10);
  return {
    battery_percent: Number.isFinite(percent) ? percent : null,
    is_charging: Number.isFinite(st) ? st === 2 : null,
  };
}

function parseNetshInterfaces(text) {
  let ssid = '';
  let bssid = '';
  let state = '';
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const lower = line.toLowerCase();
    if (lower.startsWith('ssid') && !lower.startsWith('bssid')) {
      ssid = line.split(':').slice(1).join(':').trim();
    } else if (lower.startsWith('bssid')) {
      bssid = line.split(':').slice(1).join(':').trim();
    } else if (lower.startsWith('state')) {
      state = line.split(':').slice(1).join(':').trim().toLowerCase();
    }
  }
  const isWifi = Boolean(ssid) || state.includes('connected');
  return { ssid, bssid, is_wifi: isWifi };
}

async function getDeviceInfo() {
  const [deviceId, mac, ip, battery] = await Promise.all([
    getHardwareUuid(),
    getMacAddress(),
    getIpAddress(),
    getBattery(),
  ]);
  return {
    device_id: deviceId,
    machine_name: os.hostname() || 'WorkPulseWorkstation',
    os_type: 'windows',
    os_version: `${os.type()} ${os.release()}`,
    arch: os.arch(),
    ip_address: ip,
    mac_address: mac,
    battery_percent: battery.battery_percent,
    is_charging: battery.is_charging,
    enrolled: true,
    last_heartbeat: new Date().toISOString(),
    agent_version: (() => {
      try {
        return require('../package.json').version || '0.1.0';
      } catch {
        return '0.1.0';
      }
    })(),
  };
}

async function getConnectedWifi() {
  const out = await run('netsh', ['wlan', 'show', 'interfaces']);
  const parsed = parseNetshInterfaces(out);
  return {
    ...parsed,
    timestamp: new Date().toISOString(),
  };
}

async function getWifiEvents(since) {
  const start = since && String(since).trim()
    ? String(since).trim()
    : new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
  const script = `
    $start = [datetime]::Parse('${start.replace(/'/g, "''")}')
    Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational'; Id=8001,8003; StartTime=$start} -ErrorAction SilentlyContinue |
      Sort-Object RecordId | Select-Object -Last 500 | ForEach-Object {
        $data = @{}
        foreach ($d in ([xml]$_.ToXml()).Event.EventData.Data) { $data[$d.Name] = $d.'#text' }
        "$($_.Id)|$($_.TimeCreated.ToUniversalTime().ToString('o'))|$($data['SSID'])|$($_.RecordId)"
      }
  `;
  const out = await runPs(script);
  const events = [];
  for (const line of out.split(/\r?\n/)) {
    const parts = line.trim().split('|');
    if (parts.length < 4) continue;
    const id = parts[0];
    events.push({
      kind: id === '8001' ? 'CONNECTED' : 'DISCONNECTED',
      occurred_at: parts[1],
      ssid: parts[2] || '',
      record_id: Number.parseInt(parts[3], 10) || 0,
    });
  }
  return events;
}

/**
 * Windows System log catch-up for dirty/clean shutdown and boot.
 * 6005 = startup, 6006/6008/1074 = shutdown variants.
 */
async function getPowerBootEvents(sinceIso) {
  const start =
    sinceIso && String(sinceIso).trim()
      ? String(sinceIso).trim()
      : new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
  const safeStart = start.replace(/'/g, "''");
  const script = `
    $start = [datetime]::Parse('${safeStart}')
    Get-WinEvent -FilterHashtable @{LogName='System'; Id=6005,6006,6008,1074; StartTime=$start} -ErrorAction SilentlyContinue |
      Sort-Object TimeCreated | Select-Object -Last 200 | ForEach-Object {
        $kind = switch ($_.Id) {
          6005 { 'SYSTEM_STARTUP' }
          6006 { 'SYSTEM_SHUTDOWN' }
          6008 { 'SYSTEM_SHUTDOWN' }
          1074 { 'SYSTEM_SHUTDOWN' }
          default { 'SYSTEM_SHUTDOWN' }
        }
        "$kind|$($_.TimeCreated.ToUniversalTime().ToString('o'))|$($_.Id)|$($_.RecordId)"
      }
  `;
  const out = await runPs(script);
  const events = [];
  for (const line of out.split(/\r?\n/)) {
    const parts = line.trim().split('|');
    if (parts.length < 4) continue;
    events.push({
      event_type: parts[0],
      occurred_at: parts[1],
      windows_event_id: Number.parseInt(parts[2], 10) || 0,
      record_id: Number.parseInt(parts[3], 10) || 0,
    });
  }
  return events;
}

/**
 * Foreground window: process name, title, pid.
 * Used for admin "what is each person using" — no screenshots/keylogging.
 */
async function getActiveWindow() {
  const script = `
    Add-Type @"
      using System;
      using System.Runtime.InteropServices;
      using System.Text;
      public class WinApi {
        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
      }
"@
    $hwnd = [WinApi]::GetForegroundWindow()
    $procId = 0
    [WinApi]::GetWindowThreadProcessId($hwnd, [ref]$procId) | Out-Null
    $sb = New-Object System.Text.StringBuilder 256
    [WinApi]::GetWindowText($hwnd, $sb, 256) | Out-Null
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { 'Unknown' }
    Write-Output ("{0}|{1}|{2}" -f $name, ($sb.ToString() -replace '[\\r\\n\\|]', ' '), $procId)
  `;
  const out = (await runPs(script)).trim();
  const parts = out.split('|');
  if (parts.length >= 3) {
    return {
      application_name: parts[0].trim() || 'Unknown',
      window_title: parts[1].trim() || null,
      process_id: Number.parseInt(parts[2], 10) || 0,
    };
  }
  return { application_name: 'Unknown', window_title: null, process_id: 0 };
}

module.exports = {
  saveSecureToken,
  getSecureToken,
  deleteSecureToken,
  getDeviceInfo,
  getConnectedWifi,
  getWifiEvents,
  getPowerBootEvents,
  getActiveWindow,
};
