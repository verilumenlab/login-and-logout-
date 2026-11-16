'use client';

import React, { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Eye, EyeOff, Laptop, Loader2, Lock, Mail } from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { normalizeRole, useRole, UserRole } from '@/components/RoleContext';
import { BrandLogo } from '@/components/BrandLogo';

interface DemoAccount {
  role: UserRole;
  title: string;
  email: string;
}

/** Quick-fill accounts are only offered in development builds. */
const SHOW_DEMO_ACCOUNTS = process.env.NODE_ENV === 'development';
const DEMO_PASSWORD = 'WelcomeTitan123!';
const DEMO_ACCOUNTS: DemoAccount[] = [
  { role: 'ADMIN', title: 'Administrator', email: 'admin@corp.com' },
  { role: 'HR', title: 'HR', email: 'hr@corp.com' },
  { role: 'MANAGER', title: 'Manager', email: 'manager@corp.com' },
];

export default function LoginPage() {
  const { loginUser, sessionMessage } = useRole();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [server, setServer] = useState<'checking' | 'online' | 'offline'>('checking');

  useEffect(() => {
    let cancelled = false;
    apiClient.isServerReachable().then((ok) => {
      if (!cancelled) setServer(ok ? 'online' : 'offline');
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const fillDemo = (account: DemoAccount) => {
    setEmail(account.email);
    setPassword(DEMO_PASSWORD);
    setError(null);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.login(email.trim(), password);
      if (!normalizeRole(res.user.role, res.user.is_superuser)) {
        await apiClient.logout();
        setError('Employee accounts sign in with the WorkPulse desktop app, not the web portal.');
        return;
      }
      loginUser(res.user);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign-in failed. Please check your email and password.');
    } finally {
      setLoading(false);
    }
  };

  const message = error || sessionMessage;

  return (
    <div className="min-h-[75vh] flex items-center justify-center">
      <div className="max-w-md w-full space-y-6 bg-white dark:bg-slate-900 p-8 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
        <div className="text-center space-y-3">
          <div className="flex justify-center">
            <BrandLogo href={null} variant="full" size="md" showTagline={false} />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">Sign in to WorkPulse</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">For administrators, HR and managers</p>
        </div>

        <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-2">
          <Laptop className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>
            <strong>Employees:</strong> use the WorkPulse desktop app installed on your laptop. Employee accounts cannot
            sign in here.
          </span>
        </div>

        {SHOW_DEMO_ACCOUNTS && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
              Demo accounts (development only)
            </div>
            <div className="grid grid-cols-3 gap-2">
              {DEMO_ACCOUNTS.map((acc) => {
                const selected = email === acc.email;
                return (
                  <button
                    key={acc.role}
                    type="button"
                    onClick={() => fillDemo(acc)}
                    className={`text-left p-2.5 rounded-xl border text-xs transition ${
                      selected
                        ? 'border-blue-600 bg-blue-50/60 dark:bg-blue-950/40 ring-1 ring-blue-600'
                        : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between font-semibold text-slate-800 dark:text-slate-200">
                      {acc.title}
                      {selected && <CheckCircle2 className="w-3.5 h-3.5 text-blue-600" />}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono truncate">{acc.email}</div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {message && (
          <div
            role="alert"
            className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/60 text-red-700 dark:text-red-300 text-xs flex items-start gap-2"
          >
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{message}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              Work email
            </label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
              <input
                id="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="block w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent"
              />
            </div>
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              Password
            </label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="block w-full pl-9 pr-10 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-600 disabled:opacity-50 transition"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Signing in…
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </form>

        <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
          <span
            className={`w-2 h-2 rounded-full ${
              server === 'online' ? 'bg-emerald-500' : server === 'offline' ? 'bg-rose-500' : 'bg-slate-400 animate-pulse'
            }`}
          />
          {server === 'online' ? 'Server connected' : server === 'offline' ? 'Server not reachable' : 'Checking server…'}
          <span className="font-mono text-slate-400 truncate max-w-[180px]">{apiClient.serverOrigin}</span>
        </div>
      </div>
    </div>
  );
}
