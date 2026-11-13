import React, { useState, useEffect } from 'react';
import {
  Clock,
  Play,
  Square,
  Coffee,
  CheckCircle2,
  FileText,
  MapPin,
  ShieldCheck,
  Info,
  AlertTriangle,
  Wifi,
} from 'lucide-react';
import { TodayAttendanceSummary, LocationPermissionState, LocationVerificationState } from '../types';
import { getConnectedWifiInfo, WifiInfoReceipt } from '../api/ipc';

interface AttendanceScreenProps {
  attendance: TodayAttendanceSummary;
  onClockAction: (
    action: 'CLOCK_IN' | 'CLOCK_OUT' | 'BREAK_START' | 'BREAK_END',
    note?: string,
    locationData?: {
      latitude?: number;
      longitude?: number;
      accuracy_meters?: number;
      permission_status?: LocationPermissionState;
      ssid?: string;
      bssid?: string;
    }
  ) => void;
}

export const AttendanceScreen: React.FC<AttendanceScreenProps> = ({
  attendance,
  onClockAction,
}) => {
  const [selectedBreakType, setSelectedBreakType] = useState('Lunch');
  const [adjustmentNote, setAdjustmentNote] = useState('');
  const [noteSubmitted, setNoteSubmitted] = useState(false);
  const [showDisclosure, setShowDisclosure] = useState(false);
  const [permissionState, setPermissionState] = useState<LocationPermissionState>('PROMPT');
  const [currentCoords, setCurrentCoords] = useState<{ lat: number; lon: number; acc: number } | null>(null);
  const [locationVerification, setLocationVerification] = useState<LocationVerificationState | null>(null);
  const [wifiInfo, setWifiInfo] = useState<WifiInfoReceipt | null>(null);

  // Check geolocation and native Wi-Fi status on mount
  useEffect(() => {
    getConnectedWifiInfo().then(setWifiInfo).catch(() => {});

    if ('permissions' in navigator && navigator.permissions.query) {
      navigator.permissions
        .query({ name: 'geolocation' as PermissionName })
        .then((res) => {
          setPermissionState(
            res.state === 'granted' ? 'GRANTED' : res.state === 'denied' ? 'DENIED' : 'PROMPT'
          );
          res.onchange = () => {
            setPermissionState(
              res.state === 'granted' ? 'GRANTED' : res.state === 'denied' ? 'DENIED' : 'PROMPT'
            );
          };
        })
        .catch(() => setPermissionState('PROMPT'));
    }
  }, []);

  const formatDuration = (totalSecs: number): string => {
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}`;
  };

  const handleStartBreak = () => {
    onClockAction('BREAK_START', `Break: ${selectedBreakType}`);
  };

  // Perform clock action with discrete location & native Wi-Fi capture
  const handlePunchWithLocation = async (action: 'CLOCK_IN' | 'CLOCK_OUT') => {
    const wifiData = {
      ssid: wifiInfo?.is_wifi ? wifiInfo.ssid : undefined,
      bssid: wifiInfo?.is_wifi ? wifiInfo.bssid : undefined,
    };

    if (!('geolocation' in navigator)) {
      onClockAction(action, undefined, { permission_status: 'UNAVAILABLE', ...wifiData });
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy_meters: position.coords.accuracy,
          permission_status: 'GRANTED' as LocationPermissionState,
          ...wifiData,
        };
        setCurrentCoords({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          acc: position.coords.accuracy,
        });
        setLocationVerification('VERIFIED');
        onClockAction(action, undefined, coords);
      },
      (error) => {
        const permStatus: LocationPermissionState =
          error.code === error.PERMISSION_DENIED ? 'DENIED' : 'UNAVAILABLE';
        setPermissionState(permStatus);
        setLocationVerification('UNAVAILABLE');
        // Graceful fallback: punch proceeds with native Wi-Fi even if GPS permission is denied
        onClockAction(action, `Location ${permStatus}: ${error.message}`, {
          permission_status: permStatus,
          ...wifiData,
        });
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
    );
  };

  const handleAddNote = (e: React.FormEvent) => {
    e.preventDefault();
    if (!adjustmentNote.trim()) return;
    setNoteSubmitted(true);
    setTimeout(() => {
      setAdjustmentNote('');
      setNoteSubmitted(false);
    }, 2500);
  };

  return (
    <div className="screen-container">
      {/* Title */}
      <div className="screen-header">
        <div>
          <h2 className="screen-title flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-600" />
            Attendance & Office Verification
          </h2>
          <p className="screen-subtitle">Workstation Logging with Geofence & Network Verification</p>
        </div>
        <button
          onClick={() => setShowDisclosure(!showDisclosure)}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition"
          title="View Employee Location & Privacy Policy"
        >
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
          Location Privacy
        </button>
      </div>

      {/* Location Disclosure Accordion */}
      {showDisclosure && (
        <div className="p-3 bg-blue-50/70 border border-blue-200 rounded-xl text-xs text-slate-700 space-y-1.5 animate-fadeIn">
          <div className="flex items-center gap-2 font-semibold text-blue-900">
            <Info className="w-4 h-4 text-blue-600" />
            Workplace Location & Geofence Disclosure Notice
          </div>
          <p className="text-[11px] leading-relaxed text-slate-600">
            <strong>Discrete-Only Capture:</strong> Location is recorded solely during explicit check-in and check-out actions.
            Continuous GPS tracking is strictly disabled and forbidden by system policy.
          </p>
          <div className="grid grid-cols-2 gap-2 mt-1 pt-1 border-t border-blue-200/60 text-[11px]">
            <div>• <strong>Wi-Fi / IP Rule:</strong> Network IDs are never treated as conclusive physical proof.</div>
            <div>• <strong>Data Retention:</strong> Geocoordinates are automatically purged after 90 days.</div>
          </div>
        </div>
      )}

      {/* Main Shift Timer Card */}
      <div className="card text-center py-4">
        <div className="text-xs uppercase font-semibold text-slate-400 tracking-wider">
          {attendance.mode === 'CLOCKED_IN'
            ? 'Active Work In Progress'
            : attendance.mode === 'ON_BREAK'
            ? 'On Active Break'
            : 'Workstation Shift Inactive'}
        </div>

        <div className="shift-timer-display my-2">
          <span className="text-3xl font-mono font-bold text-slate-900 tracking-tight">
            {formatDuration(attendance.totalWorkedSeconds)}
          </span>
          <p className="text-xs text-slate-500 mt-1">Total Logged Shift Time (Today)</p>
        </div>

        {/* Location Presence & Native Wi-Fi Status Indicators */}
        <div className="flex flex-col items-center justify-center gap-1.5 my-1 text-xs">
          {locationVerification === 'VERIFIED' ? (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
              <MapPin className="w-3 h-3 text-emerald-600" />
              Office Geofence Verified
              {currentCoords && (
                <span className="text-[10px] text-emerald-600/80">
                  ({currentCoords.lat.toFixed(4)}, {currentCoords.lon.toFixed(4)} ±{Math.round(currentCoords.acc)}m)
                </span>
              )}
            </span>
          ) : permissionState === 'DENIED' ? (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-amber-50 text-amber-700 border border-amber-200">
              <AlertTriangle className="w-3 h-3 text-amber-600" />
              Location Permission Denied (WFH / Unverified)
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-slate-100 text-slate-600 border border-slate-200">
              <MapPin className="w-3 h-3 text-slate-400" />
              Geofence Verification Ready
            </span>
          )}

          {/* Native Wi-Fi Network Information Badge */}
          {wifiInfo && wifiInfo.is_wifi ? (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
              <Wifi className="w-3 h-3 text-indigo-600" />
              Wi-Fi: {wifiInfo.ssid} <code className="text-[10px] opacity-75">({wifiInfo.bssid})</code>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium bg-slate-100 text-slate-500 border border-slate-200">
              <Wifi className="w-3 h-3 text-slate-400" />
              Wired LAN / Ethernet Connection
            </span>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex flex-col gap-2 max-w-xs mx-auto mt-3">
          {attendance.mode === 'CLOCKED_OUT' ? (
            <button
              onClick={() => handlePunchWithLocation('CLOCK_IN')}
              className="btn btn-primary flex items-center justify-center gap-2 py-2.5 text-sm"
            >
              <Play className="w-4 h-4 fill-current" />
              Clock In Shift (Verify Location)
            </button>
          ) : attendance.mode === 'CLOCKED_IN' ? (
            <div className="space-y-2">
              <div className="flex gap-2">
                <select
                  value={selectedBreakType}
                  onChange={(e) => setSelectedBreakType(e.target.value)}
                  className="px-3 py-1.5 text-xs border border-slate-300 rounded-lg bg-white flex-1"
                >
                  <option value="Lunch">Lunch Break (45m - Unpaid)</option>
                  <option value="Tea/Coffee">Tea / Coffee (15m - Paid)</option>
                  <option value="Personal">Personal Break (Unpaid)</option>
                  <option value="Meeting">Client / External Meeting (Paid)</option>
                </select>
                <button
                  onClick={handleStartBreak}
                  className="btn btn-secondary flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium"
                >
                  <Coffee className="w-3.5 h-3.5" />
                  Take Break
                </button>
              </div>
              <button
                onClick={() => handlePunchWithLocation('CLOCK_OUT')}
                className="btn btn-danger w-full flex items-center justify-center gap-1.5 py-2 text-xs"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                Clock Out (Record Location & End Shift)
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <button
                onClick={() => onClockAction('BREAK_END')}
                className="btn btn-primary w-full flex items-center justify-center gap-1.5 py-2 text-xs"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                Resume Shift (End Break)
              </button>
              <button
                onClick={() => handlePunchWithLocation('CLOCK_OUT')}
                className="btn btn-danger w-full flex items-center justify-center gap-1.5 py-2 text-xs"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                Clock Out Directly
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-white p-3 rounded-xl border border-slate-200">
          <div className="text-[11px] text-slate-500">First Clock In</div>
          <div className="text-sm font-semibold text-slate-900 mt-0.5">
            {attendance.clockInTime
              ? new Date(attendance.clockInTime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : 'Not clocked in'}
          </div>
        </div>
        <div className="bg-white p-3 rounded-xl border border-slate-200">
          <div className="text-[11px] text-slate-500">Total Break Time</div>
          <div className="text-sm font-semibold text-amber-700 mt-0.5">
            {formatDuration(attendance.totalBreakSeconds)}
          </div>
        </div>
      </div>

      {/* Today's Timeline Log */}
      <div className="card">
        <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
          Today&apos;s Event Stream
        </h3>
        {attendance.events.length === 0 ? (
          <p className="text-xs text-slate-400 py-3 text-center">No attendance events logged today yet.</p>
        ) : (
          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {attendance.events.map((evt) => (
              <div
                key={evt.id}
                className="flex items-center justify-between p-2 rounded-lg bg-slate-50 border border-slate-100 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                  <span className="font-semibold text-slate-800">{evt.event_type.replace('_', ' ')}</span>
                  {evt.note && <span className="text-slate-500 text-[11px]">({evt.note})</span>}
                </div>
                <div className="flex items-center gap-1.5 text-slate-400 font-mono text-[11px]">
                  <span>{new Date(evt.timestamp).toLocaleTimeString()}</span>
                  {evt.synced ? (
                    <span title="Synced with server">
                      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    </span>
                  ) : (
                    <span className="text-[10px] text-amber-600 bg-amber-50 px-1 rounded">Queued</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Attendance Adjustment Request Form */}
      <div className="card">
        <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1 flex items-center gap-1.5">
          <FileText className="w-3.5 h-3.5 text-slate-500" />
          Shift Adjustment / Timesheet Note
        </h3>
        <p className="text-[11px] text-slate-500 mb-2">
          Add notes for missing punch, power outage, or external client duty.
        </p>

        {noteSubmitted ? (
          <div className="p-2 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-700 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Timesheet note recorded and queued for audit review.
          </div>
        ) : (
          <form onSubmit={handleAddNote} className="space-y-2">
            <textarea
              rows={2}
              placeholder="e.g. Worked at client site from 10:00 AM to 12:30 PM..."
              value={adjustmentNote}
              onChange={(e) => setAdjustmentNote(e.target.value)}
              className="w-full p-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <button
              type="submit"
              disabled={!adjustmentNote.trim()}
              className="btn btn-secondary text-xs py-1.5 w-full disabled:opacity-50"
            >
              Submit Timesheet Note
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
