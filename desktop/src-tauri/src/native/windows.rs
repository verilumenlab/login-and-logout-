//! Windows 10/11 Native Integration
//!
//! Provides transparent active window inspection, idle input detection,
//! Registry-based auto-start management with explicit consent, and power telemetry.

use std::os::windows::process::CommandExt;
use std::process::Command;

use super::{normalize_since, parse_netsh_interfaces, parse_wlan_event_line, WifiEvent};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// A child process that does not flash a console window over the GUI app.
fn hidden_command(program: &str) -> Command {
    let mut cmd = Command::new(program);
    cmd.creation_flags(CREATE_NO_WINDOW);
    cmd
}

/// Retrieves the active foreground window title, process name, and PID
pub fn get_active_window_info() -> (String, String, u32) {
    let script = r#"
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
        $pid = 0
        [WinApi]::GetWindowThreadProcessId($hwnd, [ref]$pid)
        $sb = New-Object System.Text.StringBuilder 256
        [WinApi]::GetWindowText($hwnd, $sb, 256) | Out-Null
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        Write-Output "$($proc.ProcessName)|$($sb.ToString())|$pid"
    "#;

    let output = hidden_command("powershell")
        .args(["-NoProfile", "-Command", script])
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

    ("Active Desktop Window".to_string(), "Enterprise Session".to_string(), 0)
}

/// Calculates system idle duration in seconds via GetLastInputInfo
pub fn get_system_idle_seconds() -> u64 {
    let script = r#"
        Add-Type @"
            using System;
            using System.Runtime.InteropServices;
            public struct LASTINPUTINFO {
                public uint cbSize;
                public uint dwTime;
            }
            public class UserInput {
                [DllImport("user32.dll")]
                public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
            }
"@
        $lii = New-Object LASTINPUTINFO
        $lii.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($lii)
        if ([UserInput]::GetLastInputInfo([ref]$lii)) {
            $uptime = [Environment]::TickCount
            $idle = [uint32]($uptime - $lii.dwTime)
            [math]::Round($idle / 1000)
        } else {
            0
        }
    "#;

    let output = hidden_command("powershell")
        .args(["-NoProfile", "-Command", script])
        .output();

    if let Ok(out) = output {
        let val = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if let Ok(secs) = val.parse::<u64>() {
            return secs;
        }
    }

    0
}

/// Checks if auto-start is configured in Windows Registry (HKCU\Software\Microsoft\Windows\CurrentVersion\Run)
pub fn is_autostart_configured() -> bool {
    let script = r#"
        $val = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "EnterpriseAttendanceAgent" -ErrorAction SilentlyContinue
        if ($val) { "true" } else { "false" }
    "#;

    let output = hidden_command("powershell")
        .args(["-NoProfile", "-Command", script])
        .output();

    if let Ok(out) = output {
        let val = String::from_utf8_lossy(&out.stdout).trim().to_string();
        return val == "true";
    }

    false
}

/// Configures or removes Windows auto-start with explicit user consent
pub fn set_autostart(enabled: bool) -> Result<bool, String> {
    let exe_path = std::env::current_exe()
        .map_err(|e| format!("Could not get executable path: {e}"))?
        .display()
        .to_string();

    let script = if enabled {
        format!(
            r#"Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "EnterpriseAttendanceAgent" -Value '"{}"' -Force"#,
            exe_path.replace('\'', "''")
        )
    } else {
        r#"Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "EnterpriseAttendanceAgent" -ErrorAction SilentlyContinue"#.to_string()
    };

    let status = hidden_command("powershell")
        .args(["-NoProfile", "-Command", &script])
        .status()
        .map_err(|e| format!("Failed to update Windows Registry: {e}"))?;

    Ok(status.success())
}

/// Retrieves Windows hardware machine GUID and power status
pub fn get_hardware_info() -> (String, Option<u8>, bool) {
    let script = r#"
        $guid = (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Cryptography" -Name "MachineGuid" -ErrorAction SilentlyContinue).MachineGuid
        $power = Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue
        $battery = if ($power) { $power.EstimatedChargeRemaining } else { 100 }
        $charging = if ($power) { ($power.BatteryStatus -eq 2) } else { $true }
        Write-Output "$guid|$battery|$charging"
    "#;

    let output = hidden_command("powershell")
        .args(["-NoProfile", "-Command", script])
        .output();

    if let Ok(out) = output {
        let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
        let parts: Vec<&str> = text.split('|').collect();
        if parts.len() >= 3 {
            let guid = parts[0].to_string();
            let battery = parts[1].parse::<u8>().ok();
            let charging = parts[2] == "True" || parts[2] == "true";
            let effective_guid = if guid.is_empty() {
                format!("WIN-{:x}", chrono::Utc::now().timestamp())
            } else {
                format!("WIN-{guid}")
            };
            return (effective_guid, battery, charging);
        }
    }

    ("WIN-DEFAULT-HARDWARE-ID".to_string(), Some(100), true)
}

/// Checks whether the Windows workstation is currently locked
pub fn is_workstation_locked() -> bool {
    let script = r#"
        Add-Type @"
            using System;
            using System.Runtime.InteropServices;
            public class WinLockChecker {
                [DllImport("user32.dll", SetLastError = true)]
                public static extern IntPtr OpenInputDesktop(uint dwFlags, bool fInherit, uint dwDesiredAccess);
                [DllImport("user32.dll", SetLastError = true)]
                public static extern bool CloseDesktop(IntPtr hDesktop);
            }
"@
        $hDesk = [WinLockChecker]::OpenInputDesktop(0, $false, 0x0100)
        if ($hDesk -eq [IntPtr]::Zero) {
            "locked"
        } else {
            [WinLockChecker]::CloseDesktop($hDesk) | Out-Null
            "unlocked"
        }
    "#;

    let output = hidden_command("powershell")
        .args(["-NoProfile", "-Command", script])
        .output();

    if let Ok(out) = output {
        let val = String::from_utf8_lossy(&out.stdout).trim().to_string();
        return val == "locked";
    }

    false
}

/// Queries recent Windows system and session state changes from Event Log
pub fn query_recent_os_session_events(max_events: usize) -> Vec<(String, String, String)> {
    let script = format!(
        r#"
        $events = @()
        try {{
            $sec = Get-WinEvent -FilterHashtable @{{LogName='Security'; Id=4800,4801,4624,4634}} -MaxEvents {max_events} -ErrorAction SilentlyContinue | ForEach-Object {{
                $type = switch ($_.Id) {{
                    4800 {{ "SESSION_LOCK" }}
                    4801 {{ "SESSION_UNLOCK" }}
                    4624 {{ "OS_LOGON" }}
                    4634 {{ "OS_LOGOFF" }}
                    default {{ "USER_ACTIVITY" }}
                }}
                "$type|$($_.TimeCreated.ToUniversalTime().ToString('o'))|EventId $($_.Id)"
            }}
            $events += $sec
        }} catch {{}}

        try {{
            $sys = Get-WinEvent -FilterHashtable @{{LogName='System'; Id=1074,6005,6006,42,1}} -MaxEvents {max_events} -ErrorAction SilentlyContinue | ForEach-Object {{
                $type = switch ($_.Id) {{
                    1074 {{ "SYSTEM_SHUTDOWN" }}
                    6006 {{ "SYSTEM_SHUTDOWN" }}
                    6005 {{ "SYSTEM_STARTUP" }}
                    42 {{ "SYSTEM_SLEEP" }}
                    1 {{ "SYSTEM_WAKE" }}
                    default {{ "USER_ACTIVITY" }}
                }}
                "$type|$($_.TimeCreated.ToUniversalTime().ToString('o'))|EventId $($_.Id)"
            }}
            $events += $sys
        }} catch {{}}

        $events | Select-Object -First {max_events} | ForEach-Object {{ Write-Output $_ }}
        "#
    );

    let output = hidden_command("powershell")
        .args(["-NoProfile", "-Command", &script])
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

/// Queries connected Wi-Fi interface for SSID and BSSID via `netsh wlan show interfaces`
pub fn get_connected_wifi_info() -> (String, String, bool) {
    match hidden_command("netsh").args(["wlan", "show", "interfaces"]).output() {
        Ok(out) => parse_netsh_interfaces(&String::from_utf8_lossy(&out.stdout)),
        Err(_) => (String::new(), String::new(), false),
    }
}

/// Reads laptop Wi-Fi connect (8001) / disconnect (8003) events from the
/// `Microsoft-Windows-WLAN-AutoConfig/Operational` log since the given time (default: last 3 days).
/// This log is readable without administrator rights and keeps working while the app is closed,
/// so connections made before the app started are still recorded.
pub fn get_wifi_events(since: Option<&str>) -> Vec<WifiEvent> {
    let since = normalize_since(since, 3);
    let script = format!(
        r#"
        $start = [datetime]::Parse('{since}')
        Get-WinEvent -FilterHashtable @{{LogName='Microsoft-Windows-WLAN-AutoConfig/Operational'; Id=8001,8003; StartTime=$start}} -ErrorAction SilentlyContinue |
            Sort-Object RecordId | Select-Object -Last 500 | ForEach-Object {{
                $data = @{{}}
                foreach ($d in ([xml]$_.ToXml()).Event.EventData.Data) {{ $data[$d.Name] = $d.'#text' }}
                "$($_.Id)|$($_.TimeCreated.ToUniversalTime().ToString('o'))|$($data['SSID'])|$($data['ProfileName'])|$($_.RecordId)"
            }}
        "#
    );

    let Ok(out) = hidden_command("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &script])
        .output()
    else {
        return Vec::new();
    };
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .filter_map(parse_wlan_event_line)
        .collect()
}

