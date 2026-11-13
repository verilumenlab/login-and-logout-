'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  AlertCircle,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  Globe,
  HardDrive,
  Laptop,
  Mail,
  Menu,
  Shield,
  Sliders,
  UserCheck,
  Users,
  X,
  LogIn,
  LogOut,
} from 'lucide-react';
import { useRole, UserRole } from './RoleContext';
import { ThemeToggle } from './ThemeToggle';
import { apiClient } from '@/lib/api-client';

export const Navbar: React.FC = () => {
  const pathname = usePathname();
  const { role, setRole, roleLabel, user, isAuthenticated, logoutUser } = useRole();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        await apiClient.getHealth();
        setBackendOnline(true);
      } catch {
        setBackendOnline(false);
      }
    };
    checkHealth();
    const timer = setInterval(checkHealth, 30000);
    return () => clearInterval(timer);
  }, []);

  // Define navigation items scoped per role
  const getNavLinks = () => {
    switch (role) {
      case 'ADMIN':
        return [
          { href: '/', label: 'Overview', icon: Building2 },
          { href: '/employees', label: 'Employees', icon: Users },
          { href: '/departments', label: 'Departments', icon: Sliders },
          { href: '/offices', label: 'Offices & Geofences', icon: Globe },
          { href: '/devices', label: 'Device Management', icon: Laptop },
          { href: '/schedules', label: 'Report Schedules', icon: Clock },
          { href: '/audit-logs', label: 'Audit Trail', icon: Shield },
          { href: '/settings', label: 'System Settings', icon: Sliders },
        ];
      case 'HR':
        return [
          { href: '/', label: 'HR Dashboard', icon: Building2 },
          { href: '/attendance', label: 'Attendance Engine', icon: Clock },
          { href: '/activity', label: 'Computer Activity', icon: Activity },
          { href: '/locations', label: 'Location Verification', icon: Globe },
          { href: '/leave', label: 'Leave Management', icon: Calendar },
          { href: '/reports', label: 'Reports & Exports', icon: FileSpreadsheet },
          { href: '/schedules', label: 'Report Schedules', icon: Clock },
          { href: '/emails', label: 'Email Outbox', icon: Mail },
        ];
      case 'MANAGER':
        return [
          { href: '/', label: 'Team Overview', icon: Users },
          { href: '/attendance', label: 'Team Attendance', icon: Clock },
          { href: '/activity', label: 'Team Activity', icon: Activity },
          { href: '/leave', label: 'Leave Approvals', icon: Calendar },
          { href: '/reports', label: 'Team Reports', icon: FileSpreadsheet },
        ];
      case 'EMPLOYEE':
        return [
          { href: '/', label: 'My Dashboard', icon: Building2 },
          { href: '/attendance', label: 'My Attendance', icon: Clock },
          { href: '/locations', label: 'My Locations', icon: Globe },
          { href: '/leave', label: 'Leave Applications', icon: Calendar },
          { href: '/reports', label: 'My Reports', icon: FileSpreadsheet },
        ];
    }
  };

  const navLinks = getNavLinks();

  return (
    <header className="border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-900/95 backdrop-blur shadow-sm sticky top-0 z-50 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Platform Name */}
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="h-9 w-9 rounded-xl bg-blue-600 dark:bg-blue-500 flex items-center justify-center text-white font-black text-lg shadow-sm">
                E
              </div>
              <div className="hidden sm:block">
                <span className="font-bold text-slate-900 dark:text-slate-100 text-base tracking-tight">
                  Enterprise Platform
                </span>
                <span className="block text-[10px] text-slate-400 font-mono leading-none">
                  v0.1.0 • Phase 10
                </span>
              </div>
            </Link>

            {/* Backend Health Status Badge */}
            <div className="hidden md:flex items-center ml-2">
              {backendOnline === true ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  API Online
                </span>
              ) : backendOnline === false ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                  API Offline
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                  Checking...
                </span>
              )}
            </div>
          </div>

          {/* Desktop Navigation Links */}
          <nav className="hidden lg:flex items-center space-x-1">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                    isActive
                      ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400 shadow-xs'
                      : 'text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800/60'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Right Action Tools: Role Switcher, Auth & Theme Toggle */}
          <div className="flex items-center gap-2">
            {/* Enterprise Role Switcher Pill */}
            <div className="flex items-center gap-1.5 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 text-xs">
              <span className="text-[11px] text-slate-400 dark:text-slate-500 font-medium pl-1 hidden xl:inline">
                Role:
              </span>
              {(['ADMIN', 'HR', 'MANAGER', 'EMPLOYEE'] as UserRole[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setRole(r)}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold transition ${
                    role === r
                      ? 'bg-blue-600 text-white shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                  title={`Switch perspective to ${r}`}
                >
                  {r === 'ADMIN' ? 'Admin' : r === 'HR' ? 'HR' : r === 'MANAGER' ? 'Manager' : 'Employee'}
                </button>
              ))}
            </div>

            {/* User Session Profile & Sign In / Out */}
            {isAuthenticated ? (
              <div className="flex items-center gap-1.5">
                {user && (
                  <span className="hidden md:inline-block text-[11px] text-slate-600 dark:text-slate-300 font-mono truncate max-w-[120px]" title={user.email}>
                    {user.email.split('@')[0]}
                  </span>
                )}
                <button
                  onClick={() => logoutUser()}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg border border-red-200 dark:border-red-900/60 bg-red-50/80 dark:bg-red-950/40 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/60 transition"
                  title="Sign out of current account"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition"
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </Link>
            )}

            {/* Dark/Light Theme Toggle */}
            <ThemeToggle />

            {/* Mobile Menu Hamburger */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300"
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 space-y-1">
          <div className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase px-3 py-1">
            Navigation ({roleLabel})
          </div>
          {navLinks.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition ${
                  isActive
                    ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </header>
  );
};

