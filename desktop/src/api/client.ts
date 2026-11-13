/**
 * Desktop Telemetry Sync Client
 */

export interface ActivityTelemetry {
  timestamp: string;
  application_name: string;
  window_title?: string;
  duration_seconds: number;
  idle_seconds: number;
  keystrokes_count: number;
  mouse_clicks_count: number;
}

export interface AgentStatus {
  is_tracking: boolean;
  current_app: string;
  idle_seconds: number;
  un_synced_records: number;
  last_sync_time: string | null;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export async function syncActivityBatch(
  logs: ActivityTelemetry[],
  authToken?: string,
): Promise<{ synced_count: number }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  const response = await fetch(`${API_BASE_URL}/activity/sync`, {
    method: "POST",
    headers,
    body: JSON.stringify({ logs }),
  });

  if (!response.ok) {
    throw new Error(`Sync error: ${response.statusText}`);
  }

  return response.json();
}

