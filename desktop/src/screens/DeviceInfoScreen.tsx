import React, { useState } from 'react';
import {
  HardDrive,
  Laptop,
  Wifi,
  BatteryCharging,
  Battery,
  ShieldCheck,
  RefreshCw,
  CheckCircle2,
  Copy,
  Check,
} from 'lucide-react';
import { DeviceInfo } from '../types';
import { sendDeviceHeartbeat } from '../api/backend';

interface DeviceInfoScreenProps {
  deviceInfo: DeviceInfo;
  onRefresh: () => void;
}

export const DeviceInfoScreen: React.FC<DeviceInfoScreenProps> = ({
  deviceInfo,
  onRefresh,
}) => {
  const [heartbeatSending, setHeartbeatSending] = useState(false);
  const [heartbeatSuccess, setHeartbeatSuccess] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopyId = () => {
    navigator.clipboard.writeText(deviceInfo.device_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSendHeartbeat = async () => {
    try {
      setHeartbeatSending(true);
      await sendDeviceHeartbeat(deviceInfo);
      setHeartbeatSuccess(true);
      onRefresh();
      setTimeout(() => setHeartbeatSuccess(false), 3000);
    } finally {
      setHeartbeatSending(false);
    }
  };

  return (
    <div className="screen-container">
      {/* Header */}
      <div className="screen-header">
        <div>
          <h2 className="screen-title flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-indigo-600" />
            Device Information
          </h2>
          <p className="screen-subtitle">Workstation hardware identity, telemetry, and enrollment</p>
        </div>
      </div>

      {/* Hardware Fingerprint Card */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Laptop className="w-4 h-4 text-indigo-600" />
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Hardware Identity
            </h3>
          </div>
          <span className="badge badge-success flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-emerald-600" />
            Authorized Workstation
          </span>
        </div>

        <div className="space-y-2 text-xs">
          <div className="flex justify-between items-center bg-slate-50 p-2.5 rounded-lg border border-slate-100">
            <span className="text-slate-500 font-medium">Device Identifier:</span>
            <div className="flex items-center gap-1.5">
              <code className="font-mono text-xs font-bold text-slate-800 bg-white px-2 py-0.5 rounded border">
                {deviceInfo.device_id}
              </code>
              <button
                onClick={handleCopyId}
                className="p-1 hover:bg-slate-200 rounded text-slate-500"
                title="Copy Device ID"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">Host Computer Name:</span>
            <span className="font-semibold text-slate-800">{deviceInfo.machine_name}</span>
          </div>

          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">Operating System:</span>
            <span className="font-medium text-slate-800">{deviceInfo.os_version}</span>
          </div>

          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">CPU Architecture:</span>
            <span className="font-mono text-slate-800 uppercase">{deviceInfo.arch}</span>
          </div>
        </div>
      </div>

      {/* Network & Power Status Card */}
      <div className="card">
        <div className="flex items-center gap-2 mb-2">
          <Wifi className="w-4 h-4 text-blue-600" />
          <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
            Network & Power State
          </h3>
        </div>

        <div className="space-y-2 text-xs">
          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">IPv4 Address:</span>
            <span className="font-mono font-medium text-slate-800">{deviceInfo.ip_address}</span>
          </div>

          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">MAC Address:</span>
            <span className="font-mono text-slate-700">{deviceInfo.mac_address}</span>
          </div>

          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">Power Status:</span>
            <div className="flex items-center gap-1 font-medium text-slate-800">
              {deviceInfo.is_charging ? (
                <BatteryCharging className="w-4 h-4 text-emerald-600" />
              ) : (
                <Battery className="w-4 h-4 text-slate-500" />
              )}
              <span>{deviceInfo.battery_percent !== null ? `${deviceInfo.battery_percent}%` : 'AC Power'}</span>
              {deviceInfo.is_charging && <span className="text-[10px] text-emerald-600">(Plugged In)</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Agent Heartbeat & Telemetry Link */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-slate-600" />
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              Agent Telemetry Sync
            </h3>
          </div>
          <span className="text-[11px] font-mono text-slate-400">v{deviceInfo.agent_version}</span>
        </div>

        <div className="space-y-2 text-xs mb-3">
          <div className="flex justify-between items-center px-1">
            <span className="text-slate-500">Last Telemetry Heartbeat:</span>
            <span className="text-slate-800 font-medium">
              {deviceInfo.last_heartbeat
                ? new Date(deviceInfo.last_heartbeat).toLocaleTimeString()
                : 'Initial start'}
            </span>
          </div>
        </div>

        {heartbeatSuccess && (
          <div className="p-2 mb-2 bg-emerald-50 border border-emerald-200 rounded text-xs text-emerald-700 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Heartbeat dispatched and verified by server.
          </div>
        )}

        <button
          onClick={handleSendHeartbeat}
          disabled={heartbeatSending}
          className="btn btn-secondary w-full text-xs py-2 flex items-center justify-center gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${heartbeatSending ? 'animate-spin' : ''}`} />
          {heartbeatSending ? 'Dispatching Heartbeat...' : 'Send Immediate Telemetry Heartbeat'}
        </button>
      </div>
    </div>
  );
};
