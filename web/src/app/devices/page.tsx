'use client';

import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Ban,
  CheckCircle2,
  HardDrive,
  Laptop,
  Monitor,
  RefreshCw,
  Search,
  Shield,
  ShieldCheck,
  Unlock,
} from 'lucide-react';
import Link from 'next/link';
import { apiClient, Device, ReleaseSummary } from '@/lib/api-client';

export default function DeviceManagementPage() {
  const [loading, setLoading] = useState(true);
  const [devices, setDevices] = useState<Device[]>([]);
  const [search, setSearch] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [publishedVersion, setPublishedVersion] = useState<string | null>(null);

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const [data, summary] = await Promise.all([
        apiClient.listDevices().catch(() => [] as Device[]),
        apiClient.getReleaseSummary('production').catch(() => null as ReleaseSummary | null),
      ]);
      setDevices(data);
      setPublishedVersion(summary?.current_published_version || null);
    } finally {
      setLoading(false);
    }
  };

  const isOutdated = (agentVersion: string) => {
    if (!publishedVersion) return false;
    const parse = (v: string) =>
      v
        .replace(/^v/, '')
        .split('.')
        .map((p) => parseInt(p, 10) || 0);
    const a = parse(agentVersion || '0.0.0');
    const b = parse(publishedVersion);
    for (let i = 0; i < 3; i++) {
      if ((a[i] || 0) < (b[i] || 0)) return true;
      if ((a[i] || 0) > (b[i] || 0)) return false;
    }
    return false;
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleToggleBlock = async (id: string, isBlocked: boolean) => {
    setActionLoading(id);
    try {
      if (isBlocked) {
        await apiClient.unblockDevice(id);
      } else {
        await apiClient.blockDevice(id);
      }
      await fetchDevices();
    } catch (e: any) {
      alert(`Device action failed: ${e.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const displayDevices = devices;

  const filtered = displayDevices.filter((d) => {
    return (
      d.device_name.toLowerCase().includes(search.toLowerCase()) ||
      d.device_identifier.toLowerCase().includes(search.toLowerCase()) ||
      d.os_name.toLowerCase().includes(search.toLowerCase())
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Laptop className="w-6 h-6 text-blue-600" />
            Enrolled Workstation &amp; Device Management
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Audit hardware fingerprints, inspect WorkPulse Employee agent versions, and enforce session revocation
            {publishedVersion ? (
              <>
                {' '}
                · Published app:{' '}
                <Link href="/releases" className="text-blue-600 font-semibold">
                  v{publishedVersion}
                </Link>
              </>
            ) : null}
          </p>
        </div>

        <button
          onClick={fetchDevices}
          disabled={loading}
          className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filter Bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-xs">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by device name, identifier, or OS..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl text-xs bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:border-blue-500"
          />
        </div>
      </div>

      {/* Devices Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {!loading && filtered.length === 0 && (
          <p className="md:col-span-3 py-10 text-center text-xs text-slate-400">
            {devices.length === 0
              ? 'No devices yet. A laptop appears here after an employee signs in to the desktop app.'
              : 'No device matches this search.'}
          </p>
        )}
        {filtered.map((dev) => (
          <div
            key={dev.id}
            className={`bg-white dark:bg-slate-900 border rounded-2xl p-5 shadow-xs flex flex-col justify-between ${
              dev.is_blocked
                ? 'border-rose-200 dark:border-rose-900/50 bg-rose-50/20'
                : 'border-slate-200 dark:border-slate-800'
            }`}
          >
            <div>
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">
                    {dev.platform}
                  </span>
                  <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">{dev.device_name}</h3>
                </div>
                {dev.is_blocked ? (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 dark:bg-rose-950 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                    Blocked
                  </span>
                ) : (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                    Trusted
                  </span>
                )}
              </div>

              <div className="mt-4 space-y-1.5 text-xs text-slate-600 dark:text-slate-400 font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-400">ID:</span>
                  <span className="font-semibold truncate max-w-[180px]">{dev.device_identifier}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">OS:</span>
                  <span>{dev.os_name}</span>
                </div>
                <div className="flex justify-between items-center gap-2">
                  <span className="text-slate-400">Agent:</span>
                  <span className="flex items-center gap-1.5">
                    <span className="text-blue-600 font-semibold">{dev.agent_version}</span>
                    {isOutdated(dev.agent_version) && (
                      <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                        Outdated
                      </span>
                    )}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">MAC:</span>
                  <span>{dev.mac_address || '--:--:--'}</span>
                </div>
              </div>
            </div>

            <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <span className="text-[10px] text-slate-400 font-mono">
                Last seen: {dev.last_seen_at ? new Date(dev.last_seen_at).toLocaleDateString() : 'Active'}
              </span>

              <button
                onClick={() => handleToggleBlock(dev.id, dev.is_blocked)}
                disabled={actionLoading === dev.id}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1 shadow-xs disabled:opacity-50 ${
                  dev.is_blocked
                    ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                    : 'bg-rose-600 hover:bg-rose-700 text-white'
                }`}
              >
                {dev.is_blocked ? (
                  <>
                    <Unlock className="w-3.5 h-3.5" />
                    Unblock
                  </>
                ) : (
                  <>
                    <Ban className="w-3.5 h-3.5" />
                    Block Device
                  </>
                )}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

