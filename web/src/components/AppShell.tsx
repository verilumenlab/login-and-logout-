'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Loader2, LogOut, Menu, ShieldAlert, X } from 'lucide-react';
import { useRole } from './RoleContext';
import { ThemeToggle } from './ThemeToggle';
import { canAccess, NAV_BY_ROLE, PUBLIC_PATHS } from './nav-config';
import { apiClient } from '@/lib/api-client';
import { BrandLogo } from './BrandLogo';

function FullScreenLoader() {
  return (
    <div className="flex-1 flex items-center justify-center py-32 text-slate-400">
      <Loader2 className="w-6 h-6 animate-spin" />
    </div>
  );
}

function Brand() {
  return <BrandLogo href="/" variant="mark" size="md" showTagline />;
}

function ApiStatus() {
  const [online, setOnline] = useState<boolean | null>(null);
  useEffect(() => {
    const check = () =>
      apiClient
        .getHealth()
        .then(() => setOnline(true))
        .catch(() => setOnline(false));
    check();
    const timer = setInterval(check, 30000);
    return () => clearInterval(timer);
  }, []);

  if (online === null) return null;
  return online ? (
    <span className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
      Server online
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
      <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
      Server offline
    </span>
  );
}

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const pathname = usePathname();
  const router = useRouter();
  const { ready, isAuthenticated, role, roleLabel, user, logoutUser } = useRole();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const isPublic = PUBLIC_PATHS.includes(pathname);

  useEffect(() => {
    if (!ready) return;
    if (!isAuthenticated && !isPublic) router.replace('/login');
    if (isAuthenticated && isPublic) router.replace('/');
  }, [ready, isAuthenticated, isPublic, router]);

  useEffect(() => setDrawerOpen(false), [pathname]);

  if (!ready || (!isAuthenticated && !isPublic) || (isAuthenticated && isPublic)) {
    return <FullScreenLoader />;
  }

  if (isPublic) {
    return (
      <>
        <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
            <Brand />
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 w-full px-4 py-8">{children}</main>
      </>
    );
  }

  const sections = role ? NAV_BY_ROLE[role] : [];
  const allowed = role ? canAccess(role, pathname) : false;

  const handleSignOut = async () => {
    setSigningOut(true);
    await logoutUser();
    setSigningOut(false);
  };

  const nav = (
    <nav className="space-y-5">
      {sections.map((section) => (
        <div key={section.title}>
          <div className="px-3 mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            {section.title}
          </div>
          <div className="space-y-0.5">
            {section.items.map((item) => {
              const Icon = item.icon;
              const active = item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] font-medium transition ${
                    active
                      ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300'
                      : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="flex-1 flex">
      <aside className="hidden lg:flex w-60 flex-shrink-0 flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 sticky top-0 h-screen">
        <div className="h-16 px-4 flex items-center border-b border-slate-200 dark:border-slate-800">
          <Brand />
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-4">{nav}</div>
      </aside>

      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setDrawerOpen(false)} />
          <div className="relative w-64 bg-white dark:bg-slate-900 h-full shadow-xl flex flex-col">
            <div className="h-16 px-4 flex items-center justify-between border-b border-slate-200 dark:border-slate-800">
              <Brand />
              <button onClick={() => setDrawerOpen(false)} aria-label="Close menu" className="p-1.5 text-slate-500">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-4">{nav}</div>
          </div>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 sticky top-0 z-40 border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur">
          <div className="h-full px-4 sm:px-6 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setDrawerOpen(true)}
                className="lg:hidden p-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300"
                aria-label="Open menu"
              >
                <Menu className="w-4 h-4" />
              </button>
              <div className="lg:hidden">
                <Brand />
              </div>
              <ApiStatus />
            </div>

            <div className="flex items-center gap-2">
              <div className="hidden sm:flex flex-col items-end leading-tight">
                <span className="text-xs font-semibold text-slate-800 dark:text-slate-100" title={user?.email}>
                  {user?.display_name}
                </span>
                <span className="text-[10px] text-slate-500 dark:text-slate-400">{roleLabel}</span>
              </div>
              <ThemeToggle />
              <button
                onClick={handleSignOut}
                disabled={signingOut}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{signingOut ? 'Signing out…' : 'Sign out'}</span>
              </button>
            </div>
          </div>
        </header>

        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {allowed ? (
            children
          ) : (
            <div className="max-w-md mx-auto mt-16 text-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8">
              <ShieldAlert className="w-8 h-8 mx-auto text-amber-500" />
              <h2 className="mt-3 font-bold text-slate-900 dark:text-slate-100">This page isn&apos;t available</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Your {roleLabel.toLowerCase()} account doesn&apos;t have access to this section.
              </p>
              <Link
                href="/"
                className="inline-block mt-4 px-4 py-2 rounded-lg bg-blue-600 text-white text-xs font-semibold hover:bg-blue-700"
              >
                Back to overview
              </Link>
            </div>
          )}
        </main>
      </div>
    </div>
  );
};
