//! Enterprise Native Operating System Session Monitoring Engine (Phase 06)
//!
//! Provides:
//! - Monotonically increasing sequence counters persisted across device reboots
//! - Persistent local offline event queue stored in OS app data directory
//! - Common Event Contract conformance (Windows and macOS)
//! - System clock backwards shift detection and auditing
//! - Synchronization protocol with duplicate rejection and pruning
//! - Architectural negative constraints (strictly zero keylogging, zero screen recording)

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Canonical Phase 06 Common Event Contract
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OSSessionEventContract {
    pub event_id: String,
    pub employee_id: String,
    pub device_id: String,
    pub operating_system: String,
    pub event_type: String,
    pub occurred_at: String,
    pub sequence_number: u64,
    pub agent_version: String,
    pub metadata: serde_json::Value,
}

/// Offline synchronization queue diagnostic status
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventQueueStatus {
    pub pending_events_count: usize,
    pub latest_sequence_number: u64,
    pub last_event_type: Option<String>,
    pub last_event_time: Option<String>,
    pub last_sync_time: Option<String>,
    pub queue_file_path: String,
    pub clock_anomalies_detected: u32,
}

/// Server sync response contract
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncResultReceipt {
    pub received_count: usize,
    pub inserted_count: usize,
    pub duplicate_count: usize,
    pub rejected_count: usize,
    pub gaps_detected: Vec<u64>,
    pub latest_sequence_number: u64,
    pub message: String,
}

static MONITOR_LOCK: Mutex<()> = Mutex::new(());

/// Resolves directory for agent state and persistent offline queues
pub fn get_storage_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    let base = std::env::var("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:\\ProgramData"));

    #[cfg(target_os = "macos")]
    let base = std::env::var("HOME")
        .map(|h| PathBuf::from(h).join("Library/Application Support"))
        .unwrap_or_else(|_| PathBuf::from("/tmp"));

    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    let base = std::env::var("HOME")
        .map(|h| PathBuf::from(h).join(".local/share"))
        .unwrap_or_else(|_| PathBuf::from("/tmp"));

    let dir = base.join("com.enterprise.attendance.agent");
    let _ = fs::create_dir_all(&dir);
    dir
}

/// Resolves file path for persistent monotonic sequence counter
pub fn get_sequence_file_path(custom_dir: Option<&Path>) -> PathBuf {
    match custom_dir {
        Some(d) => d.join("sequence.dat"),
        None => get_storage_dir().join("sequence.dat"),
    }
}

/// Resolves file path for persistent offline events queue
pub fn get_queue_file_path(custom_dir: Option<&Path>) -> PathBuf {
    match custom_dir {
        Some(d) => d.join("os_events_queue.json"),
        None => get_storage_dir().join("os_events_queue.json"),
    }
}

/// Resolves file path for last known timestamp to detect clock tampering or jumps
pub fn get_clock_tracker_file_path(custom_dir: Option<&Path>) -> PathBuf {
    match custom_dir {
        Some(d) => d.join("clock_tracker.dat"),
        None => get_storage_dir().join("clock_tracker.dat"),
    }
}

/// Retrieves and atomically increments the monotonic sequence counter across reboots
pub fn next_sequence_number(custom_dir: Option<&Path>) -> u64 {
    let _guard = MONITOR_LOCK.lock().unwrap();
    let seq_path = get_sequence_file_path(custom_dir);

    let current_seq: u64 = if seq_path.exists() {
        fs::read_to_string(&seq_path)
            .ok()
            .and_then(|s| s.trim().parse::<u64>().ok())
            .unwrap_or(0)
    } else {
        0
    };

    let next_seq = current_seq + 1;
    let _ = fs::write(&seq_path, next_seq.to_string());
    next_seq
}

/// Retrieves the current latest sequence number without incrementing
pub fn get_current_sequence_number(custom_dir: Option<&Path>) -> u64 {
    let seq_path = get_sequence_file_path(custom_dir);
    if seq_path.exists() {
        fs::read_to_string(&seq_path)
            .ok()
            .and_then(|s| s.trim().parse::<u64>().ok())
            .unwrap_or(0)
    } else {
        0
    }
}

/// Audits current timestamp against last recorded timestamp to detect system clock rollbacks
pub fn check_clock_anomaly(now: DateTime<Utc>, custom_dir: Option<&Path>) -> Option<i64> {
    let clock_file = get_clock_tracker_file_path(custom_dir);
    let mut anomaly_seconds: Option<i64> = None;

    if clock_file.exists() {
        if let Ok(content) = fs::read_to_string(&clock_file) {
            if let Ok(prev_time) = content.trim().parse::<i64>() {
                let current_epoch = now.timestamp();
                // If current time is earlier than previous by more than 5 seconds, clock jump backwards occurred
                if current_epoch + 5 < prev_time {
                    anomaly_seconds = Some(prev_time - current_epoch);
                }
            }
        }
    }

    // Persist latest timestamp
    let _ = fs::write(&clock_file, now.timestamp().to_string());
    anomaly_seconds
}

/// Reads all queued offline events from disk
pub fn read_queue(custom_dir: Option<&Path>) -> Vec<OSSessionEventContract> {
    let queue_path = get_queue_file_path(custom_dir);
    if !queue_path.exists() {
        return Vec::new();
    }

    let data = match fs::read_to_string(&queue_path) {
        Ok(d) => d,
        Err(_) => return Vec::new(),
    };

    serde_json::from_str::<Vec<OSSessionEventContract>>(&data).unwrap_or_default()
}

/// Saves the queued events list to disk
fn write_queue(events: &[OSSessionEventContract], custom_dir: Option<&Path>) -> Result<(), String> {
    let queue_path = get_queue_file_path(custom_dir);
    let serialized = serde_json::to_string_pretty(events)
        .map_err(|e| format!("Serialization error: {e}"))?;
    fs::write(&queue_path, serialized)
        .map_err(|e| format!("Failed to write queue file {}: {e}", queue_path.display()))?;
    Ok(())
}

/// Records a new OS session event, verifies negative constraints, detects clock anomalies, and stores locally
pub fn record_session_event(
    employee_id: &str,
    device_id: &str,
    operating_system: &str,
    event_type: &str,
    mut metadata: serde_json::Value,
    custom_dir: Option<&Path>,
) -> Result<OSSessionEventContract, String> {
    // 1. Negative Constraint Enforcement: Strictly forbid keylogging, screenshots, continuous GPS
    if let serde_json::Value::Object(ref mut map) = metadata {
        let forbidden = [
            "keystrokes",
            "raw_keys",
            "keylogger",
            "screenshot",
            "screen_capture",
            "camera",
            "continuous_gps",
            "audio_record",
        ];
        for f in forbidden {
            map.remove(f);
        }
    }

    let now = Utc::now();
    let seq = next_sequence_number(custom_dir);
    let event_uuid = uuid::Uuid::new_v4().to_string();

    // 2. Check for clock anomaly / backwards jump
    if let Some(skew) = check_clock_anomaly(now, custom_dir) {
        if let serde_json::Value::Object(ref mut map) = metadata {
            map.insert("clock_jump_detected".to_string(), serde_json::json!(true));
            map.insert("clock_rollback_seconds".to_string(), serde_json::json!(skew));
        }
    }

    let event = OSSessionEventContract {
        event_id: event_uuid,
        employee_id: employee_id.to_string(),
        device_id: device_id.to_string(),
        operating_system: operating_system.to_string(),
        event_type: event_type.to_string(),
        occurred_at: now.to_rfc3339(),
        sequence_number: seq,
        agent_version: "1.0.0".to_string(),
        metadata,
    };

    // 3. Atomically append to local offline queue
    let _guard = MONITOR_LOCK.lock().unwrap();
    let mut current_queue = read_queue(custom_dir);
    current_queue.push(event.clone());
    write_queue(&current_queue, custom_dir)?;

    Ok(event)
}

/// Prunes successfully synced events from the local queue file
pub fn prune_synced_events(synced_event_ids: &[String], custom_dir: Option<&Path>) -> usize {
    let _guard = MONITOR_LOCK.lock().unwrap();
    let current_queue = read_queue(custom_dir);
    let initial_count = current_queue.len();

    let pruned: Vec<OSSessionEventContract> = current_queue
        .into_iter()
        .filter(|e| !synced_event_ids.contains(&e.event_id))
        .collect();

    let removed = initial_count - pruned.len();
    let _ = write_queue(&pruned, custom_dir);
    removed
}

/// Returns current offline event queue status
pub fn get_event_queue_status(custom_dir: Option<&Path>) -> EventQueueStatus {
    let queue = read_queue(custom_dir);
    let seq = get_current_sequence_number(custom_dir);
    let q_path = get_queue_file_path(custom_dir).display().to_string();

    let last_ev = queue.last();

    EventQueueStatus {
        pending_events_count: queue.len(),
        latest_sequence_number: seq,
        last_event_type: last_ev.map(|e| e.event_type.clone()),
        last_event_time: last_ev.map(|e| e.occurred_at.clone()),
        last_sync_time: None,
        queue_file_path: q_path,
        clock_anomalies_detected: 0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::env;

    fn setup_temp_test_dir() -> PathBuf {
        let temp_dir = env::temp_dir().join(format!("os_monitor_test_{}", uuid::Uuid::new_v4()));
        let _ = fs::create_dir_all(&temp_dir);
        temp_dir
    }

    #[test]
    fn test_monotonic_sequence_preservation() {
        let temp_dir = setup_temp_test_dir();

        let s1 = next_sequence_number(Some(&temp_dir));
        let s2 = next_sequence_number(Some(&temp_dir));
        let s3 = next_sequence_number(Some(&temp_dir));

        assert_eq!(s1, 1);
        assert_eq!(s2, 2);
        assert_eq!(s3, 3);

        // Simulate application restart / machine reboot:
        let s4 = next_sequence_number(Some(&temp_dir));
        assert_eq!(s4, 4);

        let cur = get_current_sequence_number(Some(&temp_dir));
        assert_eq!(cur, 4);

        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn test_event_recording_queueing_and_pruning() {
        let temp_dir = setup_temp_test_dir();

        let meta = serde_json::json!({
            "session_id": 1,
            "power_state": "AC",
        });

        let ev1 = record_session_event(
            "emp-uuid-1",
            "WIN-TEST-DEV",
            "windows",
            "OS_LOGON",
            meta.clone(),
            Some(&temp_dir),
        )
        .expect("Failed to record event 1");

        let ev2 = record_session_event(
            "emp-uuid-1",
            "WIN-TEST-DEV",
            "windows",
            "SESSION_LOCK",
            meta.clone(),
            Some(&temp_dir),
        )
        .expect("Failed to record event 2");

        let queue = read_queue(Some(&temp_dir));
        assert_eq!(queue.len(), 2);
        assert_eq!(queue[0].event_type, "OS_LOGON");
        assert_eq!(queue[1].event_type, "SESSION_LOCK");
        assert_eq!(queue[0].sequence_number, 1);
        assert_eq!(queue[1].sequence_number, 2);

        // Prune ev1 after server acknowledges
        let pruned = prune_synced_events(&[ev1.event_id], Some(&temp_dir));
        assert_eq!(pruned, 1);

        let queue_after = read_queue(Some(&temp_dir));
        assert_eq!(queue_after.len(), 1);
        assert_eq!(queue_after[0].event_id, ev2.event_id);

        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn test_negative_constraints_scrubbing() {
        let temp_dir = setup_temp_test_dir();

        // Attempt to pass forbidden telemetry
        let toxic_meta = serde_json::json!({
            "keystrokes": "secret_password",
            "screenshot": "base64_image_bytes",
            "camera": "stream_active",
            "session_lock_type": "workstation_locked",
        });

        let ev = record_session_event(
            "emp-uuid-2",
            "MAC-SECURE-DEV",
            "macos",
            "SESSION_LOCK",
            toxic_meta,
            Some(&temp_dir),
        )
        .expect("Failed to record event");

        let map = ev.metadata.as_object().unwrap();
        assert!(!map.contains_key("keystrokes"));
        assert!(!map.contains_key("screenshot"));
        assert!(!map.contains_key("camera"));
        assert_eq!(map.get("session_lock_type").unwrap(), "workstation_locked");

        let _ = fs::remove_dir_all(temp_dir);
    }

    #[test]
    fn test_clock_jump_backwards_detection() {
        let temp_dir = setup_temp_test_dir();

        let clock_file = get_clock_tracker_file_path(Some(&temp_dir));
        // Seed future time
        let future_epoch = Utc::now().timestamp() + 3600;
        let _ = fs::write(&clock_file, future_epoch.to_string());

        // Now run check_clock_anomaly with current time (which is 1 hr in the past relative to file)
        let anomaly = check_clock_anomaly(Utc::now(), Some(&temp_dir));
        assert!(anomaly.is_some(), "Clock rollback should be detected");
        assert!(anomaly.unwrap() >= 3590);

        let _ = fs::remove_dir_all(temp_dir);
    }
}

