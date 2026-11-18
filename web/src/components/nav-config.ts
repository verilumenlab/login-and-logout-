import {
  Building2,
  Calendar,
  Clock,
  FileSpreadsheet,
  Globe,
  HeartPulse,
  Laptop,
  LogIn,
  Mail,
  Package,
  Shield,
  ShieldAlert,
  Sliders,
  Timer,
  Users,
} from 'lucide-react';
import type { UserRole } from './RoleContext';

export interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

const OVERVIEW: NavItem = { href: '/', label: 'Overview', icon: Building2 };
const PRESENCE: NavItem = { href: '/presence', label: 'Login & Logout', icon: LogIn };
const EMPLOYEES: NavItem = { href: '/employees', label: 'Employees', icon: Users };
const DEPARTMENTS: NavItem = { href: '/departments', label: 'Departments', icon: Sliders };
const ATTENDANCE: NavItem = { href: '/attendance', label: 'Attendance', icon: Clock };
const LEAVE: NavItem = { href: '/leave', label: 'Leave', icon: Calendar };
const REPORTS: NavItem = { href: '/reports', label: 'Reports', icon: FileSpreadsheet };
const SCHEDULES: NavItem = { href: '/schedules', label: 'Report Schedules', icon: Timer };
const EMAILS: NavItem = { href: '/emails', label: 'Email Outbox', icon: Mail };
const MISSING_LOGIN: NavItem = { href: '/missing-login', label: 'Missing Login', icon: ShieldAlert }; // after 10:30 IST
const OFFICES: NavItem = { href: '/offices', label: 'Offices & Wi-Fi', icon: Globe };
const DEVICES: NavItem = { href: '/devices', label: 'Devices', icon: Laptop };
const RELEASES: NavItem = { href: '/releases', label: 'App Releases', icon: Package };
const AUDIT: NavItem = { href: '/audit-logs', label: 'Audit Trail', icon: Shield };
const HEALTH: NavItem = { href: '/health', label: 'System Health', icon: HeartPulse };
export const NAV_BY_ROLE: Record<UserRole, NavSection[]> = {
  ADMIN: [
    { title: 'Daily', items: [OVERVIEW, PRESENCE, ATTENDANCE, LEAVE, MISSING_LOGIN] },
    { title: 'People', items: [EMPLOYEES, DEPARTMENTS] },
    { title: 'Reports', items: [REPORTS, SCHEDULES, EMAILS] },
    { title: 'System', items: [OFFICES, DEVICES, RELEASES, AUDIT, HEALTH] },
  ],
  HR: [
    { title: 'Daily', items: [OVERVIEW, PRESENCE, ATTENDANCE, LEAVE, MISSING_LOGIN] },
    { title: 'People', items: [EMPLOYEES] },
    { title: 'Reports', items: [REPORTS, SCHEDULES, EMAILS] },
  ],
  // Manager portal matches HR: organization-wide people, leave, and reports.
  MANAGER: [
    { title: 'Daily', items: [OVERVIEW, PRESENCE, ATTENDANCE, LEAVE] },
    { title: 'People', items: [EMPLOYEES] },
    { title: 'Reports', items: [REPORTS, SCHEDULES, EMAILS] },
  ],
};

const REDIRECT_ONLY = ['/activity', '/locations', '/settings'];

export function canAccess(role: UserRole, pathname: string): boolean {
  if (REDIRECT_ONLY.includes(pathname)) return true;
  return NAV_BY_ROLE[role].some((section) =>
    section.items.some((item) =>
      item.href === '/' ? pathname === '/' : pathname === item.href || pathname.startsWith(`${item.href}/`)
    )
  );
}

export const PUBLIC_PATHS = ['/login'];
