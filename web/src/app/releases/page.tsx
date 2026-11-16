'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Package,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  apiClient,
  ApplicationRelease,
  DeviceUpdateStatus,
  ReleaseSummary,
  UpdateEvent,
} from '@/lib/api-client';

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    uploaded: 'bg-amber-100 text-amber-800 border-amber-200',
    approved: 'bg-sky-100 text-sky-800 border-sky-200',
    published: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    paused: 'bg-slate-100 text-slate-700 border-slate-200',
    cancelled: 'bg-rose-100 text-rose-800 border-rose-200',
    rolled_back: 'bg-orange-100 text-orange-800 border-orange-200',
  };
  return map[status] || 'bg-slate-100 text-slate-700 border-slate-200';
}

export default function ApplicationReleasesPage() {
  const [channel, setChannel] = useState('production');
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<ReleaseSummary | null>(null);
  const [releases, setReleases] = useState<ApplicationRelease[]>([]);
  const [compliance, setCompliance] = useState<DeviceUpdateStatus[]>([]);
  const [events, setEvents] = useState<UpdateEvent[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [uploadVersion, setUploadVersion] = useState('');
  const [uploadNotes, setUploadNotes] = useState('');
  const [uploadBuild, setUploadBuild] = useState('');
  const [uploadChannel, setUploadChannel] = useState('staging');
  const [setupFile, setSetupFile] = useState<File | null>(null);
  const [blockmapFile, setBlockmapFile] = useState<File | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sum, list, comp, ev] = await Promise.all([
        apiClient.getReleaseSummary(channel),
        apiClient.listReleases({ channel }),
        apiClient.getReleaseCompliance(channel),
        apiClient.listReleaseEvents(30),
      ]);
      setSummary(sum);
      setReleases(list);
      setCompliance(comp);
      setEvents(ev);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load releases');
    } finally {
      setLoading(false);
    }
  }, [channel]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const runAction = async (id: string, action: 'approve' | 'publish' | 'pause' | 'cancel' | 'rollback') => {
    setActionLoading(`${action}-${id}`);
    try {
      if (action === 'approve') await apiClient.approveRelease(id);
      if (action === 'publish') await apiClient.publishRelease(id);
      if (action === 'pause') await apiClient.pauseRelease(id);
      if (action === 'cancel') await apiClient.cancelRelease(id);
      if (action === 'rollback') await apiClient.rollbackRelease(id);
      await refresh();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setupFile || !uploadVersion.trim()) {
      alert('Version and Windows setup .exe are required');
      return;
    }
    setActionLoading('upload');
    try {
      const fd = new FormData();
      fd.append('version', uploadVersion.trim().replace(/^v/, ''));
      fd.append('channel', uploadChannel);
      if (uploadNotes.trim()) fd.append('release_notes', uploadNotes.trim());
      if (uploadBuild.trim()) fd.append('build_number', uploadBuild.trim());
      fd.append('setup_file', setupFile);
      if (blockmapFile) fd.append('blockmap_file', blockmapFile);
      await apiClient.uploadRelease(fd);
      setUploadVersion('');
      setUploadNotes('');
      setUploadBuild('');
      setSetupFile(null);
      setBlockmapFile(null);
      setChannel(uploadChannel);
      await refresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Package className="w-6 h-6 text-blue-600" />
            Employee Application Release Management
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Upload Windows Electron builds, review, publish, and monitor employee device upgrades
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
          >
            <option value="production">Production</option>
            <option value="staging">Staging</option>
          </select>
          <button
            onClick={refresh}
            disabled={loading}
            className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl"
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

      {summary?.new_release_available && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-900 px-4 py-3 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-sm">New application version uploaded</p>
            <p className="text-xs mt-0.5">
              Latest upload <strong>{summary.latest_uploaded_version}</strong> is waiting for admin review and
              publish. Current published: <strong>{summary.current_published_version || 'none'}</strong>.
            </p>
          </div>
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {[
            { label: 'Published', value: summary.current_published_version || '—' },
            { label: 'Latest upload', value: summary.latest_uploaded_version || '—' },
            { label: 'Devices', value: String(summary.registered_devices) },
            { label: 'Need update', value: String(summary.devices_needing_update) },
            { label: 'Successful', value: String(summary.successful_updates) },
            { label: 'Failed', value: String(summary.failed_updates) },
            { label: 'Channel', value: summary.channel },
          ].map((card) => (
            <div
              key={card.label}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-3"
            >
              <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">{card.label}</p>
              <p className="text-sm font-bold text-slate-900 dark:text-slate-100 mt-1 truncate">{card.value}</p>
            </div>
          ))}
        </div>
      )}

      <form
        onSubmit={handleUpload}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 space-y-4"
      >
        <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
          <Upload className="w-4 h-4" />
          Upload new Windows release
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            required
            placeholder="Version e.g. 0.1.1"
            value={uploadVersion}
            onChange={(e) => setUploadVersion(e.target.value)}
            className="text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2"
          />
          <input
            placeholder="Build number"
            value={uploadBuild}
            onChange={(e) => setUploadBuild(e.target.value)}
            className="text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2"
          />
          <select
            value={uploadChannel}
            onChange={(e) => setUploadChannel(e.target.value)}
            className="text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2"
          >
            <option value="staging">Staging</option>
            <option value="production">Production</option>
          </select>
          <input
            placeholder="Release notes"
            value={uploadNotes}
            onChange={(e) => setUploadNotes(e.target.value)}
            className="text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2 md:col-span-1"
          />
        </div>
        <div className="flex flex-col md:flex-row gap-3 items-start md:items-center">
          <label className="text-xs text-slate-600">
            Setup .exe
            <input
              type="file"
              accept=".exe"
              onChange={(e) => setSetupFile(e.target.files?.[0] || null)}
              className="block mt-1 text-xs"
            />
          </label>
          <label className="text-xs text-slate-600">
            Blockmap (optional)
            <input
              type="file"
              accept=".blockmap"
              onChange={(e) => setBlockmapFile(e.target.files?.[0] || null)}
              className="block mt-1 text-xs"
            />
          </label>
          <button
            type="submit"
            disabled={actionLoading === 'upload'}
            className="ml-auto px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 disabled:opacity-50"
          >
            {actionLoading === 'upload' ? 'Uploading…' : 'Upload release'}
          </button>
        </div>
        <p className="text-[11px] text-slate-400">
          Uploaded packages stay unpublished until an admin approves and publishes. Employees only receive published
          versions.
        </p>
      </form>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <h2 className="text-sm font-bold">Release history</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/50 text-slate-500">
              <tr>
                <th className="text-left px-4 py-2 font-semibold">Version</th>
                <th className="text-left px-4 py-2 font-semibold">Status</th>
                <th className="text-left px-4 py-2 font-semibold">OS</th>
                <th className="text-left px-4 py-2 font-semibold">Size</th>
                <th className="text-left px-4 py-2 font-semibold">Uploaded</th>
                <th className="text-left px-4 py-2 font-semibold">Notes</th>
                <th className="text-right px-4 py-2 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {releases.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No releases on this channel yet.
                  </td>
                </tr>
              )}
              {releases.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-4 py-3 font-mono font-semibold">
                    {r.version}
                    {r.build_number ? (
                      <span className="text-slate-400 font-normal"> #{r.build_number}</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full border text-[10px] font-bold ${statusBadge(r.status)}`}>
                      {r.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 capitalize">{r.os_name}</td>
                  <td className="px-4 py-3 font-mono">{formatBytes(r.package_size)}</td>
                  <td className="px-4 py-3">{new Date(r.uploaded_at).toLocaleString()}</td>
                  <td className="px-4 py-3 max-w-[200px] truncate text-slate-500">{r.release_notes || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1 flex-wrap">
                      {r.status === 'uploaded' && (
                        <button
                          onClick={() => runAction(r.id, 'approve')}
                          disabled={!!actionLoading}
                          className="px-2 py-1 rounded-lg bg-sky-600 text-white font-bold"
                          title="Approve"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {['uploaded', 'approved', 'paused', 'rolled_back'].includes(r.status) && (
                        <button
                          onClick={() => runAction(r.id, 'publish')}
                          disabled={!!actionLoading}
                          className="px-2 py-1 rounded-lg bg-emerald-600 text-white font-bold"
                          title="Publish"
                        >
                          <Play className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {r.status === 'published' && (
                        <button
                          onClick={() => runAction(r.id, 'pause')}
                          disabled={!!actionLoading}
                          className="px-2 py-1 rounded-lg bg-slate-600 text-white font-bold"
                          title="Pause"
                        >
                          <Pause className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {!['published', 'cancelled'].includes(r.status) && (
                        <button
                          onClick={() => runAction(r.id, 'cancel')}
                          disabled={!!actionLoading}
                          className="px-2 py-1 rounded-lg bg-rose-600 text-white font-bold"
                          title="Cancel"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {r.status !== 'published' && r.status !== 'cancelled' && (
                        <button
                          onClick={() => runAction(r.id, 'rollback')}
                          disabled={!!actionLoading}
                          className="px-2 py-1 rounded-lg bg-orange-600 text-white font-bold"
                          title="Rollback / re-publish this version"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <h2 className="text-sm font-bold">Employee update status</h2>
            <Link href="/devices" className="text-[11px] text-blue-600 font-semibold">
              Open devices
            </Link>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {compliance.length === 0 ? (
              <p className="px-5 py-8 text-center text-xs text-slate-400">No enrolled devices yet.</p>
            ) : (
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800/80 text-slate-500">
                  <tr>
                    <th className="text-left px-4 py-2">Device</th>
                    <th className="text-left px-4 py-2">Version</th>
                    <th className="text-left px-4 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {compliance.map((d) => (
                    <tr key={d.device_id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-4 py-2">
                        <div className="font-semibold">{d.device_name}</div>
                        <div className="font-mono text-[10px] text-slate-400 truncate max-w-[160px]">
                          {d.device_identifier}
                        </div>
                      </td>
                      <td className="px-4 py-2 font-mono">{d.installed_version || d.agent_version}</td>
                      <td className="px-4 py-2">
                        {d.needs_update ? (
                          <span className="text-amber-700 font-bold">Needs update</span>
                        ) : (
                          <span className="text-emerald-700 font-bold">Up to date</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 dark:border-slate-800">
            <h2 className="text-sm font-bold">Recent release events</h2>
          </div>
          <ul className="max-h-80 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
            {events.length === 0 && (
              <li className="px-5 py-8 text-center text-xs text-slate-400">No events yet.</li>
            )}
            {events.map((ev) => (
              <li key={ev.id} className="px-5 py-3 text-xs">
                <div className="flex justify-between gap-2">
                  <span className="font-bold uppercase text-[10px] text-slate-400">{ev.event_type}</span>
                  <span className="text-slate-400">{new Date(ev.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-1 text-slate-700 dark:text-slate-300">{ev.message || '—'}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="text-[11px] text-slate-400 flex items-center gap-1">
        <Download className="w-3.5 h-3.5" />
        Desktop apps poll the published channel feed only. Safe fleet rollback usually means shipping a new higher
        patch with reverted binaries (electron-updater rejects downgrades).
      </p>
    </div>
  );
}
