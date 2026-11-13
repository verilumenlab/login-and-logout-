import type { Metadata } from 'next';
import './globals.css';
import { RoleProvider } from '@/components/RoleContext';
import { Navbar } from '@/components/Navbar';

export const metadata: Metadata = {
  title: 'Enterprise Attendance & Activity Platform',
  description: 'Enterprise Employee Attendance, Computer Activity Tracking and Leave Management Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
        <RoleProvider>
          <Navbar />
          <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
          <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 py-4 text-center text-xs text-slate-500 dark:text-slate-400">
            Enterprise Employee Attendance, Computer Activity Tracking &amp; Leave Management Platform &copy; 2026
          </footer>
        </RoleProvider>
      </body>
    </html>
  );
}
