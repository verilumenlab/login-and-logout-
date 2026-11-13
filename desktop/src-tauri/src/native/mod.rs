//! Native OS Integrations Dispatcher

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
        ("Office_WiFi_5G".to_string(), "00:1A:2B:3C:4D:5E".to_string(), true)
    }
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
pub use generic::*;

