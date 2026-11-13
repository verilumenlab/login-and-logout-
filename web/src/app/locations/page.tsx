'use client';

import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Globe,
  Info,
  MapPin,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  Trash2,
  Wifi,
} from 'lucide-react';
import { useRole } from '@/components/RoleContext';

interface LocationRecord {
  id: string;
  employee_name: string;
  employee_code: string;
  check_type: 'CLOCK_IN' | 'CLOCK_OUT';
  verified_status: 'VERIFIED' | 'UNVERIFIED' | 'UNAVAILABLE';
  verification_method: 'GEOFENCE' | 'HYBRID_GEOFENCE_WIFI' | 'WIFI_ONLY' | 'IP_APPROXIMATE' | 'NONE';
  distance_meters: number;
  accuracy_meters: number;
  office_name: string;
  is_mock_location: boolean;
  occurred_at: string;
}

export default function LocationVerificationPage() {
  const { role } = useRole();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [purgeLoading, setPurgeLoading] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState<string | null>(null);

  // Sample verification stream matching Phase 08 schema
  const records: LocationRecord[] = [
    {
      id: 'loc-01',
      employee_name: 'Edward Employee',
      employee_code: 'EMP-7842',
      check_type: 'CLOCK_IN',
      verified_status: 'VERIFIED',
      verification_method: 'HYBRID_GEOFENCE_WIFI',
      distance_meters: 34.2,
      accuracy_meters: 8.5,
      office_name: 'Global Corp HQ (San Francisco)',
      is_mock_location: false,
      occurred_at: '2026-11-12T09:02:15Z',
    },
    {
      id: 'loc-02',
      employee_name: 'Alice Johnson',
      employee_code: 'EMP-1102',
      check_type: 'CLOCK_IN',
      verified_status: 'UNVERIFIED',
      verification_method: 'IP_APPROXIMATE',
      distance_meters: 1420.0,
      accuracy_meters: 120.0,
      office_name: 'Global Corp HQ (San Francisco)',
      is_mock_location: false,
      occurred_at: '2026-11-12T08:55:00Z',
    },
    {
      id: 'loc-03',
      employee_name: 'Mark Miller',
      employee_code: 'EMP-3391',
      check_type: 'CLOCK_IN',
      verified_status: 'VERIFIED',
      verification_method: 'GEOFENCE',
      distance_meters: 65.0,
      accuracy_meters: 12.0,
      office_name: 'East Coast Engineering Center (NYC)',
      is_mock_location: false,
      occurred_at: '2026-11-12T09:35:10Z',
    },
    {
      id: 'loc-04',
      employee_name: 'Rogue Device Test',
      employee_code: 'EMP-9999',
      check_type: 'CLOCK_IN',
      verified_status: 'UNVERIFIED',
      verification_method: 'GEOFENCE',
      distance_meters: 15.0,
      accuracy_meters: 2.0,
      office_name: 'Global Corp HQ (San Francisco)',
      is_mock_location: true,
      occurred_at: '2026-11-12T07:10:00Z',
    },
  ];

  const handlePurge = () => {
    if (!confirm('Execute compliance data retention purge for records older than 90 days?')) return;
    setPurgeLoading(true);
    setTimeout(() => {
      setPurgeLoading(false);
      setPurgeMsg('Data retention compliance purge completed: 184 obsolete coordinates purged.');
    }, 600);
  };

  const filtered = records.filter((r) => {
    const matchSearch =
      r.employee_name.toLowerCase().includes(search.toLowerCase()) ||
      r.employee_code.toLowerCase().includes(search.toLowerCase()) ||
      r.office_name.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === 'ALL' ? true : r.verified_status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <MapPin className="w-6 h-6 text-emerald-600" />
            Location &amp; Office Verification
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Physical geofence proximity evaluation, Wi-Fi confirmation, and anti-spoofing compliance
          </p>
        </div>

        {/* Retention Purge Button for Admin/HR */}
        {role !== 'EMPLOYEE' && (
          <button
            onClick={handlePurge}
            disabled={purgeLoading}
            className="px-4 py-2 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-rose-600 dark:text-rose-400 rounded-xl transition flex items-center gap-1.5 shadow-xs disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            {purgeLoading ? 'Purging...' : 'Run 90-Day Retention Purge'}
          </button>
        )}
      </div>

      {/* Compliance & Negative Constraint Disclosure Notice */}
      <div className="bg-emerald-50 dark:bg-emerald-950/40 border-l-4 border-emerald-500 p-4 rounded-r-2xl">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="text-xs text-emerald-800 dark:text-emerald-300 space-y-1">
            <h4 className="font-bold text-sm">Strict Employee Privacy &amp; Data Ethics Compliance</h4>
            <p>• <strong>Discrete Check-in Only</strong>: GPS is only sampled at the instant of Clock-In / Clock-Out. Continuous tracking is architecturally disabled.</p>
            <p>• <strong>Negative Constraints Active</strong>: Wi-Fi networks and IP addresses alone are never accepted as conclusive evidence of physical presence.</p>
            <p>• <strong>Retention Policy</strong>: High-precision coordinates are automatically purged after 90 days.</p>
          </div>
        </div>
      </div>

      {purgeMsg && (
        <div className="p-3 bg-blue-50 dark:bg-blue-950 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-xl text-xs flex justify-between items-center">
          <span>{purgeMsg}</span>
          <button onClick={() => setPurgeMsg(null)} className="font-bold ml-2">×</button>
        </div>
      )}

      {/* Filter Bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-xs flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by employee or office name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl text-xs bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:border-blue-500"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto">
          {['ALL', 'VERIFIED', 'UNVERIFIED', 'UNAVAILABLE'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                statusFilter === st
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
              }`}
            >
              {st}
            </button>
          ))}
        </div>
      </div>

      {/* Verification Records Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium">
              <tr>
                <th className="py-3 px-4 text-left">Time</th>
                <th className="py-3 px-4 text-left">Employee</th>
                <th className="py-3 px-4 text-left">Target Office Site</th>
                <th className="py-3 px-4 text-left">Proximity &amp; Accuracy</th>
                <th className="py-3 px-4 text-left">Method</th>
                <th className="py-3 px-4 text-left">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs font-mono">
              {filtered.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                  <td className="py-3 px-4 text-slate-500">
                    {new Date(item.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td className="py-3 px-4 font-sans">
                    <div className="font-semibold text-slate-900 dark:text-slate-100">{item.employee_name}</div>
                    <div className="text-[11px] text-slate-400 font-mono">{item.employee_code} • {item.check_type}</div>
                  </td>
                  <td className="py-3 px-4 font-sans text-slate-700 dark:text-slate-300">
                    {item.office_name}
                  </td>
                  <td className="py-3 px-4">
                    <div className="font-bold text-slate-800 dark:text-slate-200">
                      {item.distance_meters.toFixed(1)}m from center
                    </div>
                    <div className="text-[10px] text-slate-400">
                      GPS Accuracy: ±{item.accuracy_meters}m
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                      {item.verification_method}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                          item.verified_status === 'VERIFIED'
                            ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300'
                            : item.verified_status === 'UNVERIFIED'
                            ? 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300'
                            : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                        }`}
                      >
                        {item.verified_status}
                      </span>
                      {item.is_mock_location && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-100 text-rose-800 flex items-center gap-0.5">
                          <ShieldAlert className="w-3 h-3 text-rose-600" />
                          Spoofed Location
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

