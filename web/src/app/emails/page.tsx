'use client';

import React, { useEffect, useState } from 'react';
import {
  Loader2,
  Mail,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
} from 'lucide-react';
import { apiClient, EmailOutbox } from '@/lib/api-client';

const STATUS_STYLE: Record<EmailOutbox['status'], string> = {
  SENT: 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300',
  PENDING: 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300',
  FAILED: 'bg-rose-100 dark:bg-rose-950 text-rose-800 dark:text-rose-300',
};

export default function EmailHistoryPage() {
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [emails, setEmails] = useState<EmailOutbox[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [mailNote, setMailNote] = useState<string | null>(null);

  const fetchEmails = async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, health] = await Promise.all([
        apiClient.listEmailOutbox(100),
        apiClient.getDetailedHealth().catch(() => null),
      ]);
      setEmails(data);
      const email = (health as { email?: { delivers_to_inbox?: boolean; note?: string; provider?: string } } | null)
        ?.email;
      if (email && email.delivers_to_inbox === false) {
        setMailNote(
          email.note ||
            `Mail provider is "${email.provider || 'console'}". Messages can show SENT but are not delivered to inboxes.`
        );
      } else {
        setMailNote(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load email outbox');
      setEmails([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEmails();
  }, []);

  const filtered = emails.filter((m) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      m.recipient_email.toLowerCase().includes(q) ||
      (m.sender_email ?? '').toLowerCase().includes(q) ||
      m.subject.toLowerCase().includes(q)
    );
  });

  const handleResend = async (item: EmailOutbox) => {
    if (!confirm(`Resend this email to ${item.recipient_email}?`)) return;
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiClient.resendEmailOutbox(item.id);
      setEmails((prev) => prev.map((e) => (e.id === updated.id ? { ...e, ...updated } : e)));
      setNotice(
        updated.status === 'SENT'
          ? `Resent to ${updated.recipient_email}.`
          : `Resend queued for ${updated.recipient_email} (status: ${updated.status}).`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Resend failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (item: EmailOutbox) => {
    if (!confirm(`Delete this outbox entry for ${item.recipient_email}?`)) return;
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      await apiClient.deleteEmailOutbox(item.id);
      setEmails((prev) => prev.filter((e) => e.id !== item.id));
      setNotice('Email removed from outbox.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Mail className="w-6 h-6 text-blue-600" />
            Transactional Email Outbox &amp; Delivery Tracking
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Monitor automated notification dispatches (leave decisions, onboarding invites, and security alerts)
          </p>
        </div>

        <button
          onClick={fetchEmails}
          disabled={loading}
          className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
          aria-label="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {mailNote && (
        <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-xs">
          <strong>Mail is not reaching inboxes.</strong> {mailNote}
          <div className="mt-1">
            On Render → workpulse-api → Environment, set <code className="font-mono">EMAIL_PROVIDER=smtp</code> (Google)
            or <code className="font-mono">resend</code>, then redeploy. Resend alone only updates the outbox until that
            is configured.
          </div>
        </div>
      )}
      {error && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs">
          {error}
        </div>
      )}
      {notice && (
        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs">
          {notice}
        </div>
      )}

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-xs">
        <div className="relative w-full md:w-96">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search by to, from, or subject..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl text-xs bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:border-blue-500"
          />
        </div>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium">
              <tr>
                <th className="py-3 px-4 text-left">From</th>
                <th className="py-3 px-4 text-left">To</th>
                <th className="py-3 px-4 text-left">Subject</th>
                <th className="py-3 px-4 text-left">Status</th>
                <th className="py-3 px-4 text-left">Queued At</th>
                <th className="py-3 px-4 text-left">Dispatched At</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs font-mono">
              {loading && emails.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-10 text-center font-sans text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-10 text-center font-sans text-slate-400">
                    No emails have been sent yet.
                  </td>
                </tr>
              )}
              {filtered.map((item) => {
                const busy = busyId === item.id;
                return (
                  <tr key={item.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                    <td className="py-3.5 px-4 font-sans text-slate-700 dark:text-slate-300">
                      <div className="font-semibold text-slate-900 dark:text-slate-100">
                        {item.sender_email || '—'}
                      </div>
                      {item.sender_name && (
                        <div className="text-[10px] text-slate-500 font-sans">{item.sender_name}</div>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-semibold text-slate-900 dark:text-slate-100 font-sans">
                      {item.recipient_email}
                      {item.recipient_name && (
                        <div className="text-[10px] text-slate-500 font-normal">{item.recipient_name}</div>
                      )}
                    </td>
                    <td className="py-3.5 px-4 font-sans text-slate-700 dark:text-slate-300 max-w-xs">
                      <div className="truncate" title={item.subject}>
                        {item.subject}
                      </div>
                      {item.error_message && (
                        <div className="text-[10px] text-rose-600 mt-0.5 truncate" title={item.error_message}>
                          {item.error_message}
                        </div>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                          item.error_message?.includes('Test mode')
                            ? 'bg-amber-100 dark:bg-amber-950 text-amber-900 dark:text-amber-200'
                            : STATUS_STYLE[item.status]
                        }`}
                      >
                        {item.error_message?.includes('Test mode') ? 'LOGGED (not inbox)' : item.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-slate-500">{new Date(item.created_at).toLocaleString()}</td>
                    <td className="py-3.5 px-4 text-slate-500">
                      {item.sent_at ? new Date(item.sent_at).toLocaleString() : 'Pending'}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => handleResend(item)}
                          disabled={busy}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300 text-[11px] font-semibold font-sans hover:bg-blue-50 dark:hover:bg-blue-950/40 disabled:opacity-50"
                        >
                          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCcw className="w-3.5 h-3.5" />}
                          Resend
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(item)}
                          disabled={busy}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-rose-200 dark:border-rose-800 text-rose-600 dark:text-rose-400 text-[11px] font-semibold font-sans hover:bg-rose-50 dark:hover:bg-rose-950/40 disabled:opacity-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
