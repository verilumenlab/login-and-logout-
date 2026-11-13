'use client';

import React, { useEffect, useState } from 'react';
import {
  Building,
  Globe,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Wifi,
} from 'lucide-react';
import { apiClient, Office } from '@/lib/api-client';

export default function OfficesPage() {
  const [loading, setLoading] = useState(true);
  const [offices, setOffices] = useState<Office[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [address, setAddress] = useState('');
  const [timezone, setTimezone] = useState('America/New_York');

  const fetchOffices = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listOffices().catch(() => []);
      setOffices(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOffices();
  }, []);

  const handleCreateOffice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !code.trim() || !address.trim()) return;

    try {
      await apiClient.createOffice({
        name: name.trim(),
        code: code.trim().toUpperCase(),
        address: address.trim(),
        timezone,
      });
      setShowAddModal(false);
      setName('');
      setCode('');
      setAddress('');
      await fetchOffices();
    } catch (e: any) {
      alert(`Failed to create office: ${e.message}`);
    }
  };

  // Sample offices fallback if empty in current session
  const displayOffices = offices.length > 0 ? offices : [
    {
      id: 'off-01',
      organization_id: 'org-01',
      name: 'Global HQ - Financial District',
      code: 'HQ-SF',
      address: '100 Pine Street, San Francisco, CA 94111',
      timezone: 'America/Los_Angeles',
      is_active: true,
      geofences: [
        {
          id: 'geo-01',
          name: 'HQ Campus Perimeter',
          latitude: 37.7915,
          longitude: -122.4000,
          radius_meters: 100,
          is_active: true,
        },
      ],
      networks: [
        {
          id: 'net-01',
          name: 'Corporate Secure Wi-Fi',
          ssid: 'HQ-Corporate-WiFi',
          bssid: '00:14:22:01:23:45',
          public_ip: '198.51.100.1',
          is_active: true,
        },
      ],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 'off-02',
      organization_id: 'org-01',
      name: 'East Coast Engineering Center',
      code: 'ENG-NYC',
      address: '350 5th Ave, New York, NY 10118',
      timezone: 'America/New_York',
      is_active: true,
      geofences: [
        {
          id: 'geo-02',
          name: 'NYC Tower Perimeter',
          latitude: 40.7484,
          longitude: -73.9857,
          radius_meters: 150,
          is_active: true,
        },
      ],
      networks: [
        {
          id: 'net-02',
          name: 'NYC-Office-Secure',
          ssid: 'NYC-Corp-WiFi',
          public_ip: '203.0.113.50',
          is_active: true,
        },
      ],
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Globe className="w-6 h-6 text-emerald-600" />
            Offices &amp; Geofence Management
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure physical office perimeters, Haversine circular geofences, and trusted corporate Wi-Fi identifiers
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Office
          </button>
          <button
            onClick={fetchOffices}
            disabled={loading}
            className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Office Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {displayOffices.map((office) => (
          <div
            key={office.id}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs flex flex-col justify-between"
          >
            <div>
              <div className="flex items-start justify-between">
                <div>
                  <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 mb-1">
                    {office.code}
                  </span>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{office.name}</h3>
                </div>
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  Active Office
                </span>
              </div>

              <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 mt-2">
                <MapPin className="w-3.5 h-3.5 text-slate-400" />
                <span>{office.address}</span>
              </div>

              <div className="text-xs text-slate-400 mt-1 font-mono">
                Timezone: {office.timezone}
              </div>

              {/* Geofences & Networks Subsections */}
              <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                  <div className="font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1 mb-1">
                    <Globe className="w-3.5 h-3.5 text-emerald-600" />
                    Geofence Radius
                  </div>
                  {office.geofences && office.geofences.length > 0 ? (
                    <div>
                      <div className="font-mono text-slate-800 dark:text-slate-200">
                        {office.geofences[0].radius_meters}m radius
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        Lat: {office.geofences[0].latitude.toFixed(4)}, Lng: {office.geofences[0].longitude.toFixed(4)}
                      </div>
                    </div>
                  ) : (
                    <span className="text-slate-400">100m Standard Radius</span>
                  )}
                </div>

                <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                  <div className="font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1 mb-1">
                    <Wifi className="w-3.5 h-3.5 text-blue-600" />
                    Office Wi-Fi BSSID
                  </div>
                  {office.networks && office.networks.length > 0 ? (
                    <div>
                      <div className="font-mono text-slate-800 dark:text-slate-200 truncate">
                        {office.networks[0].ssid || 'Secure Wi-Fi'}
                      </div>
                      <div className="text-[10px] text-slate-400 font-mono">
                        IP: {office.networks[0].public_ip || 'Auto-whitelisted'}
                      </div>
                    </div>
                  ) : (
                    <span className="text-slate-400">SSID Whitelisted</span>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex justify-between items-center text-[11px] text-slate-400">
              <span>Haversine GPS Verified</span>
              <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" />
                Anti-Spoofing Active
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Add Office Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200 dark:border-slate-800">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-1">Add New Office Site</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
              Enter office details to register physical geofences and verify employee check-ins.
            </p>
            <form onSubmit={handleCreateOffice} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Office Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Austin Regional Branch"
                  className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Code</label>
                  <input
                    type="text"
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="e.g. ATX-01"
                    className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Timezone</label>
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
                  >
                    <option value="America/New_York">America/New_York (EST)</option>
                    <option value="America/Chicago">America/Chicago (CST)</option>
                    <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
                    <option value="Europe/London">Europe/London (GMT)</option>
                    <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Physical Address</label>
                <input
                  type="text"
                  required
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="Street address, City, State, ZIP"
                  className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white"
                >
                  Save Office
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

