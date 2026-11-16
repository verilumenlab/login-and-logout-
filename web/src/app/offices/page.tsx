'use client';

import React, { useEffect, useState } from 'react';
import {
  Globe,
  MapPin,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Wifi,
} from 'lucide-react';
import { apiClient, Office } from '@/lib/api-client';

function fmtCoord(n: number | null | undefined): string {
  if (typeof n !== 'number' || Number.isNaN(n)) return '—';
  return n.toFixed(4);
}

export default function OfficesPage() {
  const [loading, setLoading] = useState(true);
  const [offices, setOffices] = useState<Office[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [wifiOffice, setWifiOffice] = useState<Office | null>(null);
  const [geoOffice, setGeoOffice] = useState<Office | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [address, setAddress] = useState('');
  const [timezone, setTimezone] = useState('Asia/Kolkata');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [radius, setRadius] = useState('100');
  const [wifiName, setWifiName] = useState('');
  const [wifiSsid, setWifiSsid] = useState('');
  const [wifiIp, setWifiIp] = useState('');

  const [netName, setNetName] = useState('');
  const [netSsid, setNetSsid] = useState('');
  const [netIp, setNetIp] = useState('');
  const [netBssid, setNetBssid] = useState('');

  const [geoName, setGeoName] = useState('');
  const [geoLat, setGeoLat] = useState('');
  const [geoLng, setGeoLng] = useState('');
  const [geoRadius, setGeoRadius] = useState('100');

  const fetchOffices = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.listOffices();
      setOffices(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setOffices([]);
      setError(e instanceof Error ? e.message : 'Failed to load offices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOffices();
  }, []);

  const resetCreateForm = () => {
    setName('');
    setCode('');
    setAddress('');
    setTimezone('Asia/Kolkata');
    setLatitude('');
    setLongitude('');
    setRadius('100');
    setWifiName('');
    setWifiSsid('');
    setWifiIp('');
  };

  const handleCreateOffice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !code.trim() || !address.trim()) return;

    setActionLoading(true);
    try {
      const lat = latitude.trim() ? Number(latitude) : null;
      const lng = longitude.trim() ? Number(longitude) : null;
      const networks =
        wifiName.trim() || wifiSsid.trim() || wifiIp.trim()
          ? [
              {
                name: wifiName.trim() || wifiSsid.trim() || 'Office Wi-Fi',
                ssid: wifiSsid.trim() || null,
                ip_address: wifiIp.trim() || null,
                is_active: true,
              },
            ]
          : undefined;

      await apiClient.createOffice({
        name: name.trim(),
        code: code.trim().toUpperCase(),
        address: address.trim(),
        timezone,
        latitude: lat,
        longitude: lng,
        radius_meters: radius.trim() ? Number(radius) : 100,
        networks,
      });
      setShowAddModal(false);
      resetCreateForm();
      await fetchOffices();
    } catch (err: unknown) {
      alert(`Failed to create office: ${err instanceof Error ? err.message : 'Unknown error'}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddWifi = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!wifiOffice) return;
    if (!netName.trim() && !netSsid.trim()) {
      alert('Enter a network name or SSID');
      return;
    }
    setActionLoading(true);
    try {
      await apiClient.addNetwork(wifiOffice.id, {
        name: netName.trim() || netSsid.trim() || 'Office Wi-Fi',
        ssid: netSsid.trim() || null,
        ip_address: netIp.trim() || null,
        bssid_mac: netBssid.trim() || null,
        is_active: true,
      });
      setWifiOffice(null);
      setNetName('');
      setNetSsid('');
      setNetIp('');
      setNetBssid('');
      await fetchOffices();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to add Wi-Fi');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddGeofence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!geoOffice) return;
    const lat = Number(geoLat);
    const lng = Number(geoLng);
    if (Number.isNaN(lat) || Number.isNaN(lng)) {
      alert('Enter valid latitude and longitude');
      return;
    }
    setActionLoading(true);
    try {
      await apiClient.addGeofence(geoOffice.id, {
        name: geoName.trim() || `${geoOffice.name} Perimeter`,
        latitude: lat,
        longitude: lng,
        radius_meters: Number(geoRadius) || 100,
      });
      setGeoOffice(null);
      setGeoName('');
      setGeoLat('');
      setGeoLng('');
      setGeoRadius('100');
      await fetchOffices();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to add geofence');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteNetwork = async (officeId: string, networkId: string) => {
    if (!confirm('Remove this Wi-Fi network?')) return;
    try {
      await apiClient.deleteNetwork(officeId, networkId);
      await fetchOffices();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete network');
    }
  };

  const handleDeleteOffice = async (office: Office) => {
    if (!confirm(`Delete office "${office.name}" (${office.code})?`)) return;
    try {
      await apiClient.deleteOffice(office.id);
      await fetchOffices();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to delete office');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Globe className="w-6 h-6 text-emerald-600" />
            Offices &amp; Wi-Fi
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure office locations, GPS geofences, and trusted corporate Wi-Fi networks
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

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-sm px-4 py-3">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {loading && (
          <p className="md:col-span-2 py-10 text-center text-xs text-slate-400">Loading offices…</p>
        )}
        {!loading && offices.length === 0 && (
          <p className="md:col-span-2 py-10 text-center text-xs text-slate-400">
            No offices yet. Add an office and its Wi-Fi networks so laptop connections count as login/logout.
          </p>
        )}
        {offices.map((office) => {
          const geofences = office.geofences || [];
          const networks = office.networks || [];
          return (
            <div
              key={office.id}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 mb-1">
                      {office.code}
                    </span>
                    <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{office.name}</h3>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                      office.is_active
                        ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${office.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`}
                    />
                    {office.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 mt-2">
                  <MapPin className="w-3.5 h-3.5 text-slate-400" />
                  <span>{office.address}</span>
                </div>
                <div className="text-xs text-slate-400 mt-1 font-mono">Timezone: {office.timezone}</div>

                <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-800 space-y-3 text-xs">
                  <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                    <div className="font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between gap-2 mb-2">
                      <span className="flex items-center gap-1">
                        <Globe className="w-3.5 h-3.5 text-emerald-600" />
                        Geofences ({geofences.length})
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setGeoOffice(office);
                          setGeoName(`${office.name} Perimeter`);
                        }}
                        className="text-[10px] font-bold text-blue-600 hover:underline"
                      >
                        + Add
                      </button>
                    </div>
                    {geofences.length === 0 ? (
                      <span className="text-slate-400">No geofence configured</span>
                    ) : (
                      <ul className="space-y-1.5">
                        {geofences.map((g) => (
                          <li key={g.id} className="font-mono text-slate-700 dark:text-slate-300">
                            <div className="font-semibold text-slate-800 dark:text-slate-200">{g.name}</div>
                            <div className="text-[10px] text-slate-400">
                              {g.radius_meters}m · Lat {fmtCoord(g.latitude)}, Lng {fmtCoord(g.longitude)}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-slate-100 dark:border-slate-800">
                    <div className="font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between gap-2 mb-2">
                      <span className="flex items-center gap-1">
                        <Wifi className="w-3.5 h-3.5 text-blue-600" />
                        Wi-Fi Networks ({networks.length})
                      </span>
                      <button
                        type="button"
                        onClick={() => setWifiOffice(office)}
                        className="text-[10px] font-bold text-blue-600 hover:underline"
                      >
                        + Add
                      </button>
                    </div>
                    {networks.length === 0 ? (
                      <span className="text-slate-400">No Wi-Fi configured</span>
                    ) : (
                      <ul className="space-y-2">
                        {networks.map((n) => (
                          <li
                            key={n.id}
                            className="flex items-start justify-between gap-2 font-mono text-slate-700 dark:text-slate-300"
                          >
                            <div className="min-w-0">
                              <div className="font-semibold truncate">{n.ssid || n.name || 'Secure Wi-Fi'}</div>
                              <div className="text-[10px] text-slate-400">
                                IP: {n.ip_address || '—'}
                                {n.bssid_mac ? ` · BSSID: ${n.bssid_mac}` : ''}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => handleDeleteNetwork(office.id, n.id)}
                              className="text-rose-500 hover:text-rose-700 p-0.5"
                              title="Remove Wi-Fi"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex justify-between items-center text-[11px] text-slate-400">
                <button
                  type="button"
                  onClick={() => handleDeleteOffice(office)}
                  className="text-rose-500 hover:text-rose-700 font-semibold"
                >
                  Delete office
                </button>
                <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  Verified site
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {showAddModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200 dark:border-slate-800 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-1">Add New Office</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
              Register the site, optional GPS perimeter, and office Wi-Fi.
            </p>
            <form onSubmit={handleCreateOffice} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Office Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Hyderabad HQ"
                  className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
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
                    placeholder="e.g. HYD-01"
                    className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Timezone</label>
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  >
                    <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                    <option value="America/New_York">America/New_York (EST)</option>
                    <option value="America/Chicago">America/Chicago (CST)</option>
                    <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
                    <option value="Europe/London">Europe/London (GMT)</option>
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
                  className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>

              <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                <p className="text-[11px] font-bold text-slate-500 uppercase mb-2">Optional geofence</p>
                <div className="grid grid-cols-3 gap-2">
                  <input
                    type="number"
                    step="any"
                    placeholder="Latitude"
                    value={latitude}
                    onChange={(e) => setLatitude(e.target.value)}
                    className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                  <input
                    type="number"
                    step="any"
                    placeholder="Longitude"
                    value={longitude}
                    onChange={(e) => setLongitude(e.target.value)}
                    className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                  <input
                    type="number"
                    placeholder="Radius (m)"
                    value={radius}
                    onChange={(e) => setRadius(e.target.value)}
                    className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                <p className="text-[11px] font-bold text-slate-500 uppercase mb-2">Optional office Wi-Fi</p>
                <div className="space-y-2">
                  <input
                    type="text"
                    placeholder="Network label"
                    value={wifiName}
                    onChange={(e) => setWifiName(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      placeholder="SSID"
                      value={wifiSsid}
                      onChange={(e) => setWifiSsid(e.target.value)}
                      className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                    />
                    <input
                      type="text"
                      placeholder="Public / office IP"
                      value={wifiIp}
                      onChange={(e) => setWifiIp(e.target.value)}
                      className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false);
                    resetCreateForm();
                  }}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
                >
                  {actionLoading ? 'Saving…' : 'Save Office'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {wifiOffice && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200 dark:border-slate-800">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-1 flex items-center gap-2">
              <Wifi className="w-5 h-5 text-blue-600" />
              Add Wi-Fi — {wifiOffice.name}
            </h3>
            <form onSubmit={handleAddWifi} className="space-y-3 mt-4">
              <input
                type="text"
                placeholder="Network name"
                value={netName}
                onChange={(e) => setNetName(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              />
              <input
                type="text"
                placeholder="SSID"
                value={netSsid}
                onChange={(e) => setNetSsid(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              />
              <input
                type="text"
                placeholder="Public / office IP"
                value={netIp}
                onChange={(e) => setNetIp(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              />
              <input
                type="text"
                placeholder="BSSID MAC (optional)"
                value={netBssid}
                onChange={(e) => setNetBssid(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              />
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setWifiOffice(null)} className="px-4 py-2 text-xs font-semibold text-slate-600">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 text-white disabled:opacity-50"
                >
                  Save Wi-Fi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {geoOffice && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200 dark:border-slate-800">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-1">Add Geofence — {geoOffice.name}</h3>
            <form onSubmit={handleAddGeofence} className="space-y-3 mt-4">
              <input
                type="text"
                placeholder="Perimeter name"
                value={geoName}
                onChange={(e) => setGeoName(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  step="any"
                  required
                  placeholder="Latitude"
                  value={geoLat}
                  onChange={(e) => setGeoLat(e.target.value)}
                  className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
                <input
                  type="number"
                  step="any"
                  required
                  placeholder="Longitude"
                  value={geoLng}
                  onChange={(e) => setGeoLng(e.target.value)}
                  className="px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                />
              </div>
              <input
                type="number"
                placeholder="Radius meters"
                value={geoRadius}
                onChange={(e) => setGeoRadius(e.target.value)}
                className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              />
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setGeoOffice(null)} className="px-4 py-2 text-xs font-semibold text-slate-600">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 text-white disabled:opacity-50"
                >
                  Save Geofence
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
