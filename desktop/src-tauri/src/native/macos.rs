//! macOS Native Integration
//!
//! Provides transparent active window tracking via NSWorkspace / System Events,
//! HID idle time inspection, LaunchAgent auto-start configuration, and power telemetry.

use std::fs;
use std::path::PathBuf;
use std::process::Command;

/// Retrieves macOS frontmost application name and window title
pub fn get_active_window_info() -> (String, String, u32) {
    let script = r#"
        tell application "System Events"
            set frontProc to first application process whose frontmost is true
            set procName to name of frontProc
            set procId to unix id of frontProc
            set winTitle to ""
            try
                set winTitle to name of first window of frontProc
            end try
            return procName & "|" & winTitle & "|" & procId
        end tell
    "#;

    let output = Command::new("/usr/bin/osascript")
        .args(["-e", script])
        .output();

    if let Ok(out) = output {
        let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
        let parts: Vec<&str> = text.split('|').collect();
        if parts.len() >= 3 {
            let app_name = parts[0].to_string();
            let title = parts[1].to_string();
            let pid = parts[2].parse::<u32>().unwrap_or(0);
            return (app_name, title, pid);
        }
    }

    ("Finder".to_string(), "Desktop".to_string(), 0)
}

/// Retrieves system idle time in seconds using IOHIDSystem
pub fn get_system_idle_seconds() -> u64 {
    let output = Command::new("sh")
        .args(["-c", "ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print int($NF/1000000000); exit}'"])
        .output();

    if let Ok(out) = output {
        let val = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if let Ok(secs) = val.parse::<u64>() {
            return secs;
        }
    }

    0
}

fn get_plist_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    PathBuf::from(home).join("Library/LaunchAgents/com.enterprise.attendance.agent.plist")
}

/// Checks whether the user has authorized auto-start via LaunchAgents
pub fn is_autostart_configured() -> bool {
    get_plist_path().exists()
}

/// Configures or removes macOS LaunchAgent with user consent
pub fn set_autostart(enabled: bool) -> Result<bool, String> {
    let plist_path = get_plist_path();

    if enabled {
        let exe_path = std::env::current_exe()
            .map_err(|e| format!("Executable resolution error: {e}"))?
            .display()
            .to_string();

        let plist_content = format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.enterprise.attendance.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"#,
            exe = exe_path
        );

        if let Some(parent) = plist_path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        fs::write(&plist_path, plist_content)
            .map_err(|e| format!("Failed to create LaunchAgent plist: {e}"))?;
        Ok(true)
    } else {
        if plist_path.exists() {
            let _ = fs::remove_file(plist_path);
        }
        Ok(false)
    }
}

/// Retrieves macOS hardware UUID and battery state
pub fn get_hardware_info() -> (String, Option<u8>, bool) {
    let uuid_out = Command::new("sh")
        .args(["-c", "ioreg -rd1 -c IOPlatformExpertDevice | awk -F'\"' '/IOPlatformUUID/{print $4}'"])
        .output();

    let hardware_uuid = if let Ok(out) = uuid_out {
        let u = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if u.is_empty() {
            "MAC-HARDWARE-UNKNOWN".to_string()
        } else {
            format!("MAC-{u}")
        }
    } else {
        "MAC-DEFAULT-NODE".to_string()
    };

    let batt_out = Command::new("pmset")
        .args(["-g", "batt"])
        .output();

    let mut percent: Option<u8> = None;
    let mut charging = true;

    if let Ok(out) = batt_out {
        let text = String::from_utf8_lossy(&out.stdout);
        charging = text.contains("AC Power") || text.contains("charging");
        if let Some(pos) = text.find('%') {
            let slice = &text[..pos];
            if let Some(num_start) = slice.rfind(|c: char| !c.is_numeric()) {
                percent = slice[num_start + 1..].parse::<u8>().ok();
            }
        }
    }

    (hardware_uuid, percent, charging)
}

/// Checks whether macOS screen is currently locked
pub fn is_workstation_locked() -> bool {
    let output = Command::new("sh")
        .args(["-c", "python3 -c \"import Quartz; d=Quartz.CGSessionCopyCurrentDictionary(); print(d.get('CGSSessionScreenIsLocked', 0))\" 2>/dev/null || echo 0"])
        .output();

    if let Ok(out) = output {
        let val = String::from_utf8_lossy(&out.stdout).trim().to_string();
        return val == "1" || val == "True";
    }

    false
}

/// Queries recent macOS power and session events from pmset and syslog
pub fn query_recent_os_session_events(max_events: usize) -> Vec<(String, String, String)> {
    let script = format!(
        r#"pmset -g log | grep -E "Sleep|Wake" | tail -n {max_events} | while read -r line; do
            if echo "$line" | grep -q "Sleep"; then
                echo "SYSTEM_SLEEP|$(date -u +%Y-%m-%dT%H:%M:%SZ)|$line"
            elif echo "$line" | grep -q "Wake"; then
                echo "SYSTEM_WAKE|$(date -u +%Y-%m-%dT%H:%M:%SZ)|$line"
            fi
        done"#
    );

    let output = Command::new("sh")
        .args(["-c", &script])
        .output();

    let mut results = Vec::new();
    if let Ok(out) = output {
        let text = String::from_utf8_lossy(&out.stdout);
        for line in text.lines() {
            let parts: Vec<&str> = line.trim().split('|').collect();
            if parts.len() >= 3 {
                results.push((parts[0].to_string(), parts[1].to_string(), parts[2].to_string()));
            }
        }
    }

    results
}

/// Queries connected Wi-Fi interface for SSID via airport or networksetup
pub fn get_connected_wifi_info() -> (String, String, bool) {
    let output = Command::new("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport")
        .arg("-I")
        .output();

    if let Ok(out) = output {
        let text = String::from_utf8_lossy(&out.stdout);
        let mut ssid = String::new();
        let mut bssid = String::new();
        for line in text.lines() {
            let line = line.trim();
            if line.starts_with("SSID:") {
                ssid = line.replace("SSID:", "").trim().to_string();
            } else if line.starts_with("BSSID:") {
                bssid = line.replace("BSSID:", "").trim().to_string();
            }
        }
        if !ssid.is_empty() {
            return (ssid, bssid, true);
        }
    }

    ("macOS Corporate Network".to_string(), "00:00:00:00:00:00".to_string(), false)
}

