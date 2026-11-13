'use client';

import React from 'react';

export const AttendanceTrendChart: React.FC<{
  data?: { day: string; present: number; remote: number; onLeave: number }[];
}> = ({
  data = [
    { day: 'Mon', present: 88, remote: 8, onLeave: 4 },
    { day: 'Tue', present: 92, remote: 5, onLeave: 3 },
    { day: 'Wed', present: 90, remote: 6, onLeave: 4 },
    { day: 'Thu', present: 86, remote: 9, onLeave: 5 },
    { day: 'Fri', present: 82, remote: 12, onLeave: 6 },
  ],
}) => {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <span className="font-medium">Attendance & WFH Distribution (Last 5 Workdays)</span>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> In-Office</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-blue-500"></span> Remote/WFH</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span> On Leave</span>
        </div>
      </div>
      <div className="grid grid-cols-5 gap-3 h-40 items-end pt-4 pb-2 border-b border-slate-100 dark:border-slate-800">
        {data.map((item) => (
          <div key={item.day} className="flex flex-col items-center h-full justify-end group">
            <div className="w-full max-w-[40px] flex flex-col items-center h-full justify-end gap-0.5 relative">
              {/* Tooltip */}
              <div className="absolute -top-10 opacity-0 group-hover:opacity-100 bg-slate-900 text-white text-[10px] py-1 px-2 rounded shadow transition pointer-events-none whitespace-nowrap z-10">
                {item.day}: {item.present}% In-Office, {item.remote}% Remote, {item.onLeave}% Leave
              </div>
              <div
                style={{ height: `${item.onLeave}%` }}
                className="w-full bg-amber-400 dark:bg-amber-500 rounded-t-sm"
              />
              <div
                style={{ height: `${item.remote}%` }}
                className="w-full bg-blue-500 dark:bg-blue-600"
              />
              <div
                style={{ height: `${item.present}%` }}
                className="w-full bg-emerald-500 dark:bg-emerald-600 rounded-b-sm"
              />
            </div>
            <span className="text-xs font-semibold text-slate-600 dark:text-slate-400 mt-2">{item.day}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const ActivityDistributionChart: React.FC<{
  activeHours?: number;
  idleHours?: number;
  breakHours?: number;
}> = ({ activeHours = 6.4, idleHours = 0.8, breakHours = 1.0 }) => {
  const total = activeHours + idleHours + breakHours;
  const activePct = Math.round((activeHours / total) * 100);
  const idlePct = Math.round((idleHours / total) * 100);
  const breakPct = 100 - activePct - idlePct;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-2xl font-bold text-slate-900 dark:text-slate-100">{activeHours}h</div>
          <div className="text-xs text-slate-500 dark:text-slate-400">Avg. Daily Active Computer Time</div>
        </div>
        <div className="text-right">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-300">
            {activePct}% Productivity
          </span>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="w-full h-3 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden flex">
        <div style={{ width: `${activePct}%` }} className="bg-emerald-500" title={`Active: ${activeHours}h`} />
        <div style={{ width: `${idlePct}%` }} className="bg-amber-400" title={`Idle: ${idleHours}h`} />
        <div style={{ width: `${breakPct}%` }} className="bg-slate-300 dark:bg-slate-600" title={`Breaks: ${breakHours}h`} />
      </div>

      <div className="grid grid-cols-3 text-center text-xs pt-1">
        <div>
          <div className="font-bold text-slate-800 dark:text-slate-200">{activeHours}h ({activePct}%)</div>
          <div className="text-[11px] text-emerald-600 font-medium">● Active Focus</div>
        </div>
        <div>
          <div className="font-bold text-slate-800 dark:text-slate-200">{idleHours}h ({idlePct}%)</div>
          <div className="text-[11px] text-amber-600 font-medium">● Idle / Inactive</div>
        </div>
        <div>
          <div className="font-bold text-slate-800 dark:text-slate-200">{breakHours}h ({breakPct}%)</div>
          <div className="text-[11px] text-slate-500 font-medium">● Break Time</div>
        </div>
      </div>
    </div>
  );
};

