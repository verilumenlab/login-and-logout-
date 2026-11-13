//! Native OS Integrations Dispatcher

use chrono::{DateTime, SecondsFormat, Utc};
use serde::Serialize;

/// A laptop Wi-Fi connection change read from the OS log.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct WifiEvent {
    /// "CONNECTED" or "DISCONNECTED"
    pub kind: String,
    /// RFC 3339 UTC timestamp (millisecond precision)
    pub occurred_at: String,
    pub ssid: String,
    /// Stable per-machine id of the log record, used for de-duplication
    pub record_id: u64,
}

/// Parses one `EventId|TimeCreatedUtc|SSID|ProfileName|RecordId` line from the WLAN-AutoConfig log query.
pub fn parse_wlan_event_line(line: &str) -> Option<WifiEvent> {
    let parts: Vec<&str> = line.trim().splitn(5, '|').collect();
    if parts.len() != 5 {
        return None;
    }
    let kind = match parts[0] {
        "8001" => "CONNECTED",
        "8003" => "DISCONNECTED",
        _ => return None,
    };
    let occurred_at = DateTime::parse_from_rfc3339(parts[1])
        .ok()?
        .with_timezone(&Utc)
        .to_rfc3339_opts(SecondsFormat::Millis, true);
    let ssid = if parts[2].trim().is_empty() { parts[3] } else { parts[2] };
    Some(WifiEvent {
        kind: kind.to_string(),
        occurred_at,
        ssid: ssid.trim().to_string(),
        record_id: parts[4].trim().parse().ok()?,
    })
}

/// Parses `netsh wlan show interfaces` output into (ssid, bssid, connected).
pub fn parse_netsh_interfaces(text: &str) -> (String, String, bool) {
    let mut ssid = String::new();
    let mut bssid = String::new();
    let mut connected = false;

    for line in text.lines() {
        let Some((key, value)) = line.trim().split_once(':') else {
            continue;
        };
        let key = key.trim();
        let value = value.trim();
        match key {
            "State" => connected = value.eq_ignore_ascii_case("connected"),
            "SSID" => ssid = value.to_string(),
            "BSSID" | "AP BSSID" => bssid = value.to_string(),
            _ => {}
        }
    }
    if !connected {
        return (String::new(), String::new(), false);
    }
    (ssid, bssid, true)
}

/// Normalizes a caller-supplied RFC 3339 timestamp so it can be embedded safely in a query.
pub fn normalize_since(since: Option<&str>, fallback_days: i64) -> String {
    since
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|d| d.with_timezone(&Utc))
        .unwrap_or_else(|| Utc::now() - chrono::Duration::days(fallback_days))
        .to_rfc3339_opts(SecondsFormat::Secs, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_wlan_connect_and_disconnect_lines() {
        let ev = parse_wlan_event_line("8001|2026-11-12T06:38:07.0589852Z|Work Nest 2.4G|Work Nest 2.4G|3717").unwrap();
        assert_eq!(ev.kind, "CONNECTED");
        assert_eq!(ev.occurred_at, "2026-11-12T06:38:07.058Z");
        assert_eq!(ev.ssid, "Work Nest 2.4G");
        assert_eq!(ev.record_id, 3717);

        let ev = parse_wlan_event_line("8003|2026-11-12T12:00:00Z||Office|3720").unwrap();
        assert_eq!(ev.kind, "DISCONNECTED");
        assert_eq!(ev.ssid, "Office");

        assert!(parse_wlan_event_line("8002|2026-11-12T12:00:00Z|x|x|1").is_none());
        assert!(parse_wlan_event_line("garbage").is_none());
    }

    #[test]
    fn netsh_disconnected_is_not_connected() {
        let connected = "    State                  : connected\n    SSID                   : Office 5G\n    AP BSSID               : aa:bb:cc:dd:ee:ff\n";
        assert_eq!(
            parse_netsh_interfaces(connected),
            ("Office 5G".to_string(), "aa:bb:cc:dd:ee:ff".to_string(), true)
        );
        let disconnected = "    State                  : disconnected\n";
        assert!(!parse_netsh_interfaces(disconnected).2);
    }

    #[test]
    fn since_is_normalized() {
        assert_eq!(normalize_since(Some("2026-11-12T06:38:07.123+05:30"), 3), "2026-11-12T01:08:07Z");
        assert!(normalize_since(Some("'; Remove-Item C:\\"), 3).ends_with('Z'));
    }
}

#[cfg(target_os = "windows")]
pub mod windows;
#[cfg(target_os = "windows")]
pub use windows::*;

#[cfg(target_os = "macos")]
pub mod macos;
#[cfg(target_os = "macos")]
pub use macos::*;

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub mod generic {
    pub fn get_active_window_info() -> (String, String, u32) {
        ("X11 Application".to_string(), "Linux Desktop".to_string(), 1000)
    }

    pub fn get_system_idle_seconds() -> u64 {
        0
    }

    pub fn is_autostart_configured() -> bool {
        false
    }

    pub fn set_autostart(_enabled: bool) -> Result<bool, String> {
        Ok(false)
    }

    pub fn get_hardware_info() -> (String, Option<u8>, bool) {
        ("GENERIC-NODE-UUID".to_string(), Some(100), true)
    }

    pub fn is_workstation_locked() -> bool {
        false
    }

    pub fn query_recent_os_session_events(_max_events: usize) -> Vec<(String, String, String)> {
        Vec::new()
    }

    pub fn get_connected_wifi_info() -> (String, String, bool) {
        (String::new(), String::new(), false)
    }

    pub fn get_wifi_events(_since: Option<&str>) -> Vec<super::WifiEvent> {
        Vec::new()
    }
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub use generic::*;

