'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ShieldCheck,
  Lock,
  Mail,
  Eye,
  EyeOff,
  Loader2,
  AlertCircle,
  Building2,
  UserCheck,
  Briefcase,
  Users,
  CheckCircle2,
} from 'lucide-react';
import { apiClient } from '@/lib/api-client';
import { useRole, UserRole } from '@/components/RoleContext';

interface DemoAccount {
  role: UserRole;
  title: string;
  email: string;
  badgeColor: string;
  description: string;
}

const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    role: 'ADMIN',
    title: 'Administrator',
    email: 'admin@corp.com',
    badgeColor: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
    description: 'System management, organization settings, device control & full access',
  },
  {
    role: 'HR',
    title: 'HR Representative',
    email: 'hr@corp.com',
    badgeColor: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
    description: 'Employee onboarding, attendance review, 2nd-tier leave approvals & exports',
  },
  {
    role: 'MANAGER',
    title: 'Department Manager',
    email: 'manager@corp.com',
    badgeColor: 'bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border-blue-200 dark:border-blue-800',
    description: 'Team attendance monitoring, daily logs & 1st-tier leave approvals',
  },
  {
    role: 'EMPLOYEE',
    title: 'Employee',
    email: 'employee@corp.com',
    badgeColor: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-300 dark:border-slate-700',
    description: 'Personal attendance records, working hours & leave applications',
  },
];

export default function LoginPage() {
  const router = useRouter();
  const { loginUser } = useRole();

  const [email, setEmail] = useState('admin@corp.com');
  const [password, setPassword] = useState('WelcomeTitan123!');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<UserRole>('ADMIN');

  const selectDemoRole = (account: DemoAccount) => {
    setActiveTab(account.role);
    setEmail(account.email);
    setPassword('WelcomeTitan123!');
    setError(null);
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError('Please provide both corporate email and password.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await apiClient.login(email.trim(), password);
      loginUser(res.access_token, res.user);

      // Redirect to home/employees dashboard
      router.push('/employees');
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[85vh] flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white dark:bg-slate-900 p-8 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800 transition-colors">
        {/* Brand Header */}
        <div className="text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-gradient-to-tr from-indigo-600 to-blue-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <Building2 className="h-6 w-6" />
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Enterprise Platform Portal
          </h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Secure Authentication for Admin, HR, Manager & Employee
          </p>
        </div>

        {/* Quick Role Selection Tabs */}
        <div>
          <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
            Select Role / Quick Fill
          </label>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((acc) => {
              const isSelected = activeTab === acc.role;
              return (
                <button
                  key={acc.role}
                  type="button"
                  onClick={() => selectDemoRole(acc)}
                  className={`flex flex-col text-left p-2.5 rounded-xl border text-xs transition-all ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50/50 dark:bg-indigo-950/40 ring-1 ring-indigo-600'
                      : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {acc.title}
                    </span>
                    {isSelected && <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />}
                  </div>
                  <span className="text-[10px] text-slate-500 dark:text-slate-400 font-mono mt-0.5 truncate">
                    {acc.email}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800/60 text-red-700 dark:text-red-300 text-xs flex items-start gap-2 animate-fadeIn">
            <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Authentication Error</p>
              <p className="mt-0.5 text-[11px]">{error}</p>
            </div>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
              Corporate Email Address
            </label>
            <div className="relative mt-1">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Mail className="h-4 w-4" />
              </div>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@corp.com"
                className="block w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent transition-colors"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                Password
              </label>
              <span className="text-[10px] text-indigo-600 dark:text-indigo-400">
                Default: WelcomeTitan123!
              </span>
            </div>
            <div className="relative mt-1">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                <Lock className="h-4 w-4" />
              </div>
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="block w-full pl-9 pr-10 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-600 shadow-md shadow-indigo-600/20 disabled:opacity-50 transition-all"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Signing In...</span>
              </>
            ) : (
              <span>Sign In as {DEMO_ACCOUNTS.find((a) => a.role === activeTab)?.title || 'User'}</span>
            )}
          </button>
        </form>

        {/* Security Footer */}
        <div className="pt-4 border-t border-slate-100 dark:border-slate-800 text-center">
          <div className="inline-flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            <ShieldCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Enterprise Argon2id & Rotating JWT Protection</span>
          </div>
        </div>
      </div>
    </div>
  );
}

