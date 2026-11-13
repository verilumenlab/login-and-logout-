//! Telemetry & System Information Models

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceInfo {
    pub device_id: String,
    pub machine_name: String,
    pub os_type: String,
    pub os_version: String,
    pub arch: String,
    pub ip_address: String,
    pub mac_address: String,
    pub battery_percent: Option<u8>,
    pub is_charging: Option<bool>,
    pub enrolled: bool,
    pub last_heartbeat: Option<String>,
    pub agent_version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActiveWindowInfo {
    pub application_name: String,
    pub window_title: String,
    pub process_id: u32,
    pub idle_seconds: u64,
    pub is_tracking: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityTelemetry {
    pub timestamp: String,
    pub application_name: String,
    pub window_title: Option<String>,
    pub duration_seconds: u32,
    pub idle_seconds: u32,
    pub keystrokes_count: u32,
    pub mouse_clicks_count: u32,
}

