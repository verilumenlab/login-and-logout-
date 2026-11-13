pub mod native;
pub mod session_monitor;
pub mod storage;
pub mod telemetry;

use telemetry::{ActiveWindowInfo, ActivityTelemetry, DeviceInfo};

#[tauri::command]
fn save_secure_token(key: String, value: String) -> Result<(), String> {
    storage::save_token(&key, &value)
}

#[tauri::command]
fn get_secure_token(key: String) -> Result<Option<String>, String> {
    storage::get_token(&key)
}

#[tauri::command]
fn delete_secure_token(key: String) -> Result<(), String> {
    storage::delete_token(&key)
}

#[tauri::command]
fn get_device_info() -> DeviceInfo {
    let (hardware_uuid, battery, charging) = native::get_hardware_info();

    let machine_name = std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_else(|_| "EnterpriseWorkstation".to_string());

    let os_type = std::env::consts::OS.to_string();
    let arch = std::env::consts::ARCH.to_string();

    let os_version = if cfg!(target_os = "windows") {
        "Windows 11 Enterprise (64-bit)".to_string()
    } else if cfg!(target_os = "macos") {
        "macOS Sonoma 14.5".to_string()
    } else {
        format!("Linux ({})", std::env::consts::OS)
    };

    DeviceInfo {
        device_id: hardware_uuid,
        machine_name,
        os_type,
        os_version,
        arch,
        ip_address: "192.168.1.108".to_string(),
        mac_address: "00:1A:2B:3C:4D:5E".to_string(),
        battery_percent: battery,
        is_charging: Some(charging),
        enrolled: true,
        last_heartbeat: Some(chrono::Utc::now().to_rfc3339()),
        agent_version: "0.1.0-tauri2".to_string(),
    }
}

#[tauri::command]
fn get_active_window() -> ActiveWindowInfo {
    let (app, title, pid) = native::get_active_window_info();
    let idle = native::get_system_idle_seconds();

    ActiveWindowInfo {
        application_name: app,
        window_title: title,
        process_id: pid,
        idle_seconds: idle,
        is_tracking: true,
    }
}

#[tauri::command]
fn get_autostart_status() -> bool {
    native::is_autostart_configured()
}

#[tauri::command]
fn set_autostart(enabled: bool) -> Result<bool, String> {
    native::set_autostart(enabled)
}

#[tauri::command]
fn get_connected_wifi() -> serde_json::Value {
    let (ssid, bssid, is_wifi) = native::get_connected_wifi_info();
    serde_json::json!({
        "ssid": ssid,
        "bssid": bssid,
        "is_wifi": is_wifi,
        "timestamp": chrono::Utc::now().to_rfc3339(),
    })
}

#[tauri::command]
fn send_desktop_notification(title: String, body: String) -> Result<(), String> {
    println!("[DESKTOP NOTIFICATION] {}: {}", title, body);
    Ok(())
}

// Backward compatibility endpoints
#[tauri::command]
fn get_agent_status() -> serde_json::Value {
    let (app, _, _) = native::get_active_window_info();
    let idle = native::get_system_idle_seconds();
    serde_json::json!({
        "is_tracking": true,
        "current_app": app,
        "idle_seconds": idle,
        "os": std::env::consts::OS,
    })
}

#[tauri::command]
fn collect_activity_telemetry() -> ActivityTelemetry {
    let (app, title, _) = native::get_active_window_info();
    ActivityTelemetry {
        timestamp: chrono::Utc::now().to_rfc3339(),
        application_name: app,
        window_title: Some(title),
        duration_seconds: 60,
        idle_seconds: 0,
        keystrokes_count: 42,
        mouse_clicks_count: 12,
    }
}

// ============================================================================
// Phase 06: Native Operating System Session Monitoring Commands
// ============================================================================

#[tauri::command]
fn get_os_session_events() -> Vec<session_monitor::OSSessionEventContract> {
    session_monitor::read_queue(None)
}

#[tauri::command]
fn get_event_queue_status() -> session_monitor::EventQueueStatus {
    session_monitor::get_event_queue_status(None)
}

#[tauri::command]
fn is_workstation_locked() -> bool {
    native::is_workstation_locked()
}

#[tauri::command]
fn record_os_session_event(
    employee_id: String,
    device_id: String,
    event_type: String,
    metadata: serde_json::Value,
) -> Result<session_monitor::OSSessionEventContract, String> {
    let os = std::env::consts::OS;
    session_monitor::record_session_event(
        &employee_id,
        &device_id,
        os,
        &event_type,
        metadata,
        None,
    )
}

#[tauri::command]
fn simulate_os_session_transition(
    employee_id: String,
    device_id: String,
    event_type: String,
) -> Result<session_monitor::OSSessionEventContract, String> {
    let os = std::env::consts::OS;
    let meta = serde_json::json!({
        "simulation_trigger": "Manual Verification Test",
        "workstation_locked": native::is_workstation_locked(),
        "battery_info": native::get_hardware_info().1,
        "disclosure": "Session transition logged transparently for attendance compliance."
    });
    session_monitor::record_session_event(
        &employee_id,
        &device_id,
        os,
        &event_type,
        meta,
        None,
    )
}

#[tauri::command]
async fn sync_os_session_events(
    api_url: String,
    auth_token: String,
) -> Result<session_monitor::SyncResultReceipt, String> {
    let events = session_monitor::read_queue(None);
    if events.is_empty() {
        return Ok(session_monitor::SyncResultReceipt {
            received_count: 0,
            inserted_count: 0,
            duplicate_count: 0,
            rejected_count: 0,
            gaps_detected: Vec::new(),
            latest_sequence_number: session_monitor::get_current_sequence_number(None),
            message: "Local queue is empty; nothing to sync.".to_string(),
        });
    }

    let sync_endpoint = format!("{}/api/v1/os-events/sync", api_url.trim_end_matches('/'));

    let client = reqwest::Client::new();
    let body = serde_json::json!({
        "events": events
    });

    let resp = client
        .post(&sync_endpoint)
        .header("Authorization", format!("Bearer {}", auth_token))
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Failed to dispatch sync request: {e}"))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let err_text = resp.text().await.unwrap_or_default();
        return Err(format!("Server returned error {}: {}", status, err_text));
    }

    let receipt: session_monitor::SyncResultReceipt = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse sync receipt: {e}"))?;

    // Prune acknowledged events from local queue
    let synced_ids: Vec<String> = events.iter().map(|e| e.event_id.clone()).collect();
    session_monitor::prune_synced_events(&synced_ids, None);

    Ok(receipt)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            save_secure_token,
            get_secure_token,
            delete_secure_token,
            get_device_info,
            get_active_window,
            get_autostart_status,
            set_autostart,
            send_desktop_notification,
            get_agent_status,
            collect_activity_telemetry,
            get_os_session_events,
            get_event_queue_status,
            is_workstation_locked,
            record_os_session_event,
            simulate_os_session_transition,
            sync_os_session_events,
            get_connected_wifi
        ])
        .run(tauri::generate_context!())
        .expect("error while running enterprise attendance desktop application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_storage_lifecycle() {
        let key = "test_auth_token_key";
        let secret = "jwt.header.payload.signature_test_12345";

        // Save
        let res_save = storage::save_token(key, secret);
        assert!(res_save.is_ok(), "Failed to save secret in vault");

        // Read
        let res_read = storage::get_token(key);
        assert!(res_read.is_ok(), "Failed to read secret from vault");
        let opt_token = res_read.unwrap();
        assert!(opt_token.is_some(), "Token not found in vault");
        assert_eq!(opt_token.unwrap(), secret, "Decrypted token mismatch");

        // Delete
        let res_del = storage::delete_token(key);
        assert!(res_del.is_ok(), "Failed to delete token from vault");

        // Verify gone
        let res_after = storage::get_token(key);
        assert!(
            res_after.unwrap().is_none(),
            "Token should no longer exist after deletion"
        );
    }

    #[test]
    fn test_device_info_generation() {
        let info = get_device_info();
        assert!(!info.device_id.is_empty(), "Device ID must not be empty");
        assert!(!info.machine_name.is_empty(), "Machine name must not be empty");
        assert_eq!(info.arch, std::env::consts::ARCH);
        assert_eq!(info.os_type, std::env::consts::OS);
        assert!(info.enrolled);
    }

    #[test]
    fn test_active_window_detection() {
        let win = get_active_window();
        assert!(!win.application_name.is_empty());
        assert!(win.is_tracking);
    }

    #[test]
    fn test_autostart_query() {
        // Querying status should never panic
        let _ = get_autostart_status();
    }

    #[test]
    fn test_phase6_os_session_events_lifecycle() {
        let temp_dir = std::env::temp_dir().join(format!("test_phase6_{}", uuid::Uuid::new_v4()));
        let _ = std::fs::create_dir_all(&temp_dir);

        let initial_status = session_monitor::get_event_queue_status(Some(&temp_dir));
        assert_eq!(initial_status.pending_events_count, 0);

        // Record logon
        let ev_logon = session_monitor::record_session_event(
            "emp-uuid-alpha",
            "TEST-HARDWARE-01",
            std::env::consts::OS,
            "OS_LOGON",
            serde_json::json!({"session": "active"}),
            Some(&temp_dir),
        ).expect("Logon recording failed");

        assert_eq!(ev_logon.sequence_number, 1);
        assert_eq!(ev_logon.event_type, "OS_LOGON");

        // Record lock
        let ev_lock = session_monitor::record_session_event(
            "emp-uuid-alpha",
            "TEST-HARDWARE-01",
            std::env::consts::OS,
            "SESSION_LOCK",
            serde_json::json!({"trigger": "timeout"}),
            Some(&temp_dir),
        ).expect("Lock recording failed");

        assert_eq!(ev_lock.sequence_number, 2);

        let queue = session_monitor::read_queue(Some(&temp_dir));
        assert_eq!(queue.len(), 2);

        // Prune logon event
        let pruned = session_monitor::prune_synced_events(&[ev_logon.event_id], Some(&temp_dir));
        assert_eq!(pruned, 1);

        let queue_after = session_monitor::read_queue(Some(&temp_dir));
        assert_eq!(queue_after.len(), 1);
        assert_eq!(queue_after[0].event_id, ev_lock.event_id);

        let _ = std::fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn test_workstation_locked_check() {
        // Querying workstation lock state should execute cleanly without panic
        let _ = is_workstation_locked();
    }
}
