'use client';

import { useState, useEffect } from 'react';
import { DetailedHealthStatus, apiClient } from '@/lib/api-client';

export default function HealthPage() {
  const [backendHealth, setBackendHealth] = useState<DetailedHealthStatus | null>(null);
  const [frontendHealth, setFrontendHealth] = useState<{ status: string; timestamp: string } | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch frontend self-health
      const feRes = await fetch('/api/health');
      if (feRes.ok) {
        setFrontendHealth(await feRes.json());
      }

      // Fetch backend health
      const beData = await apiClient.getDetailedHealth();
      setBackendHealth(beData);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to reach backend health endpoint');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Platform System Health</h1>
          <p className="text-sm text-slate-500 mt-1">Live status of web, backend, database, and message brokers</p>
        </div>
        <button
          onClick={fetchHealth}
          disabled={loading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white rounded-lg text-sm font-medium transition"
        >
          {loading ? 'Refreshing...' : 'Refresh Status'}
        </button>
      </div>

      {/* Overview Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Next.js Frontend */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-600">Frontend (Next.js)</span>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
              Online
            </span>
          </div>
          <div className="mt-4 text-xs text-slate-500 space-y-1">
            <p>Service: enterprise-attendance-web</p>
            <p>Route: /api/health</p>
            <p>Checked: {frontendHealth?.timestamp || 'Just now'}</p>
          </div>
        </div>

        {/* Backend API */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-600">Backend API (FastAPI)</span>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                backendHealth?.status === 'healthy'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-amber-100 text-amber-800'
              }`}
            >
              {backendHealth?.status || (error ? 'Offline / Unreachable' : 'Checking')}
            </span>
          </div>
          <div className="mt-4 text-xs text-slate-500 space-y-1">
            <p>Version: {backendHealth?.version || '0.1.0'}</p>
            <p>Environment: {backendHealth?.environment || 'development'}</p>
            <p>Uptime: {backendHealth ? `${backendHealth.uptime_seconds}s` : 'N/A'}</p>
          </div>
        </div>

        {/* Database */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-600">Database Engine</span>
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                backendHealth?.database.status === 'healthy'
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-700'
              }`}
            >
              {backendHealth?.database.status || 'Pending Check'}
            </span>
          </div>
          <div className="mt-4 text-xs text-slate-500 space-y-1">
            <p>Dialect: {backendHealth?.database.database || 'PostgreSQL'}</p>
            <p>Latency: {backendHealth?.database.latency_ms ? `${backendHealth.database.latency_ms} ms` : 'N/A'}</p>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 p-4 rounded-xl text-sm">
          <strong>Notice:</strong> {error}. Ensure FastAPI is running on port 8000 (<code>npm run dev</code> or <code>uvicorn app.main:app</code>).
        </div>
      )}

      {/* Raw Health JSON Viewer */}
      {backendHealth && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-3">Diagnostic Telemetry Payload</h3>
          <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg text-xs overflow-x-auto font-mono">
            {JSON.stringify(backendHealth, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

