'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  User,
  ArrowLeft,
  Mail,
  Phone,
  Building2,
  Calendar,
  Briefcase,
  Clock,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  Edit,
  Save,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import { apiClient, ASSIGNABLE_ROLES, Department, Employee, EmployeeUpdate, roleLabel } from '@/lib/api-client';
import { useRole } from '@/components/RoleContext';

export default function EmployeeDetailsPage() {
  const router = useRouter();
  const { role: myRole, user: me } = useRole();
  const [employeeId, setEmployeeId] = useState<string | null>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('id');
    if (id) setEmployeeId(id);
    else router.replace('/employees');
  }, [router]);

  const [employee, setEmployee] = useState<Employee | null>(null);
  const [allEmployees, setAllEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Edit Mode
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<EmployeeUpdate>({});
  const [actionLoading, setActionLoading] = useState(false);

  const fetchEmployeeData = async () => {
    if (!employeeId) return;
    setLoading(true);
    setError(null);
    try {
      const [emp, depts, dir] = await Promise.all([
        apiClient.getEmployee(employeeId),
        apiClient.listDepartments(),
        apiClient.listEmployees({ page: 1, page_size: 100 }),
      ]);
      setEmployee(emp);
      setDepartments(depts);
      setAllEmployees(dir.items);
      setEditForm({
        first_name: emp.first_name,
        last_name: emp.last_name,
        employee_code: emp.employee_code,
        phone: emp.phone || '',
        job_title: emp.job_title || '',
        department_id: emp.department_id || '',
        manager_id: emp.manager?.id || '',
        hr_rep_id: emp.hr_rep?.id || '',
        hire_date: emp.hire_date,
        employment_status: emp.employment_status,
        role_name: emp.role_name || 'Employee',
      });
    } catch (err: any) {
      setError(err.message || 'Failed to load employee details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (employeeId) {
      fetchEmployeeData();
    }
  }, [employeeId]);

  const handleToggleStatus = async () => {
    if (!employee) return;
    const newStatus = !employee.is_active;
    if (confirm(`Are you sure you want to ${newStatus ? 'activate' : 'deactivate'} this account?`)) {
      setActionLoading(true);
      try {
        await apiClient.toggleEmployeeStatus(employee.id, newStatus);
        setSuccessMsg(`Account status updated to ${newStatus ? 'Active' : 'Inactive'}.`);
        fetchEmployeeData();
      } catch (err: any) {
        setError(err.message || 'Failed to update account status');
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!employeeId) return;
    setActionLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await apiClient.updateEmployee(employeeId, {
        ...editForm,
        department_id: editForm.department_id || undefined,
        manager_id: editForm.manager_id || undefined,
        hr_rep_id: editForm.hr_rep_id || undefined,
      });
      setIsEditing(false);
      setSuccessMsg('Employee profile saved successfully.');
      fetchEmployeeData();
    } catch (err: any) {
      setError(err.message || 'Failed to update employee profile');
    } finally {
      setActionLoading(false);
    }
  };

  const isOwnProfile = !!employee && !!me && employee.user_id === me.id;
  const roleOptions = ASSIGNABLE_ROLES.filter(
    (r) => !r.adminOnly || myRole === 'ADMIN' || r.value === employee?.role_name
  );
  const canChangeRole =
    !isOwnProfile && (myRole === 'ADMIN' || !ASSIGNABLE_ROLES.find((r) => r.value === employee?.role_name)?.adminOnly);

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center gap-3 text-slate-500">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        <p className="text-sm font-medium">Loading employee profile...</p>
      </div>
    );
  }

  if (!employee) {
    return (
      <div className="py-16 text-center space-y-4">
        <AlertCircle className="w-12 h-12 text-red-500 mx-auto" />
        <h2 className="text-xl font-bold text-slate-900">Employee Record Not Found</h2>
        <p className="text-sm text-slate-500">The requested employee does not exist or you lack permission to view it.</p>
        <Link
          href="/employees"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Directory
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <Link
          href="/employees"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-900 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Employees
        </Link>
        <div className="flex items-center gap-3">
          <button
            onClick={handleToggleStatus}
            disabled={actionLoading}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition ${
              employee.is_active
                ? 'border-rose-300 text-rose-700 hover:bg-rose-50'
                : 'border-emerald-300 text-emerald-700 hover:bg-emerald-50'
            }`}
          >
            {employee.is_active ? 'Deactivate Account' : 'Activate Account'}
          </button>
          {!isEditing ? (
            <button
              onClick={() => setIsEditing(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg shadow-sm transition"
            >
              <Edit className="w-4 h-4" />
              Edit Profile
            </button>
          ) : (
            <button
              onClick={() => setIsEditing(false)}
              className="px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 text-sm font-medium rounded-lg transition"
            >
              Cancel Edit
            </button>
          )}
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-red-700 font-medium">{error}</div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
            &times;
          </button>
        </div>
      )}

      {successMsg && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-emerald-800 font-medium">{successMsg}</div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-600">
            &times;
          </button>
        </div>
      )}

      {/* Main Hero Header Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div className="flex items-center gap-5">
          <div className="w-20 h-20 rounded-2xl bg-blue-600 text-white font-extrabold flex items-center justify-center text-3xl shadow-sm">
            {employee.first_name[0]}
            {employee.last_name[0]}
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-slate-900">{employee.full_name}</h1>
              <span className="font-mono text-xs font-semibold bg-slate-100 text-slate-800 px-2.5 py-1 rounded-md border border-slate-200">
                {employee.employee_code}
              </span>
              <span className="text-xs font-semibold bg-blue-50 text-blue-700 px-2.5 py-1 rounded-full border border-blue-200">
                {roleLabel(employee.role_name)}
              </span>
            </div>
            <div className="text-sm font-medium text-slate-600 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-slate-400" />
              {employee.job_title || 'No Job Title Specified'}
              <span className="text-slate-300">•</span>
              <Building2 className="w-4 h-4 text-slate-400" />
              {employee.department ? employee.department.name : 'Unassigned Division'}
            </div>
          </div>
        </div>

        <div className="flex flex-col md:items-end gap-1.5 self-stretch md:self-auto border-t md:border-t-0 pt-4 md:pt-0 border-slate-100">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-full ${
              employee.is_active
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-rose-50 text-rose-700 border border-rose-200'
            }`}
          >
            {employee.is_active ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {employee.is_active ? 'Active Account' : 'Inactive Account'}
          </span>
          <span className="text-xs text-slate-400">
            Employment Status: <strong className="text-slate-700 uppercase">{employee.employment_status}</strong>
          </span>
        </div>
      </div>

      {/* Profile Form (View or Edit) */}
      {isEditing ? (
        <form onSubmit={handleSaveProfile} className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
          <h2 className="text-base font-bold text-slate-900 border-b border-slate-200 pb-3 flex items-center gap-2">
            <Edit className="w-4 h-4 text-blue-600" />
            Edit Profile & Assignments
          </h2>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">Role</label>
            <select
              value={editForm.role_name || 'Employee'}
              disabled={!canChangeRole}
              onChange={(e) => setEditForm({ ...editForm, role_name: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-50 disabled:text-slate-500"
            >
              {roleOptions.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}: {r.hint}
                </option>
              ))}
            </select>
            {!canChangeRole && (
              <p className="text-xs text-slate-400 mt-1">
                {isOwnProfile
                  ? 'You cannot change your own role.'
                  : 'Only an administrator can change an administrator’s role.'}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">First Name *</label>
              <input
                type="text"
                required
                value={editForm.first_name || ''}
                onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Last Name *</label>
              <input
                type="text"
                required
                value={editForm.last_name || ''}
                onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Employee Code / ID *</label>
              <input
                type="text"
                required
                value={editForm.employee_code || ''}
                onChange={(e) => setEditForm({ ...editForm, employee_code: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Job Title</label>
              <input
                type="text"
                value={editForm.job_title || ''}
                onChange={(e) => setEditForm({ ...editForm, job_title: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Phone Number</label>
              <input
                type="text"
                value={editForm.phone || ''}
                onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Department</label>
              <select
                value={editForm.department_id || ''}
                onChange={(e) => setEditForm({ ...editForm, department_id: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Unassigned</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.code})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Reporting Manager</label>
              <select
                value={editForm.manager_id || ''}
                onChange={(e) => setEditForm({ ...editForm, manager_id: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">No Manager</option>
                {allEmployees
                  .filter((e) => e.id !== employee.id && e.employee_code !== 'ADMIN-001')
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} ({e.employee_code})
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">HR Representative</label>
              <select
                value={editForm.hr_rep_id || ''}
                onChange={(e) => setEditForm({ ...editForm, hr_rep_id: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select HR Representative</option>
                {allEmployees
                  .filter((e) => e.id !== employee.id && e.employee_code !== 'ADMIN-001')
                  .map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name} ({e.employee_code})
                    </option>
                  ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Hire / Joining Date *</label>
              <input
                type="date"
                required
                value={editForm.hire_date || ''}
                onChange={(e) => setEditForm({ ...editForm, hire_date: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Employment Status</label>
              <select
                value={editForm.employment_status || 'ACTIVE'}
                onChange={(e) => setEditForm({ ...editForm, employment_status: e.target.value })}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="ACTIVE">ACTIVE</option>
                <option value="ON_LEAVE">ON LEAVE</option>
                <option value="PROBATION">PROBATION</option>
                <option value="TERMINATED">TERMINATED</option>
              </select>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={actionLoading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm transition disabled:opacity-50 flex items-center gap-2"
            >
              {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Profile Changes
            </button>
          </div>
        </form>
      ) : (
        /* View Mode: Categorized Information Cards */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Card 1: Personal & Contact Details */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
              <User className="w-4 h-4 text-blue-600" />
              Contact & Identity Information
            </h2>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-xs text-slate-400 block">Corporate Email</span>
                <span className="font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Mail className="w-4 h-4 text-slate-400" />
                  {employee.email}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-400 block">Phone Number</span>
                <span className="font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Phone className="w-4 h-4 text-slate-400" />
                  {employee.phone || 'Not provided'}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-400 block">System Identifier (UUID)</span>
                <span className="font-mono text-xs text-slate-600 bg-slate-50 px-2 py-1 rounded block mt-0.5 select-all">
                  {employee.id}
                </span>
              </div>
            </div>
          </div>

          {/* Card 2: Organizational Assignments */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
              <Building2 className="w-4 h-4 text-blue-600" />
              Organizational Hierarchy
            </h2>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-xs text-slate-400 block">Assigned Department</span>
                <span className="font-medium text-slate-900 block mt-0.5">
                  {employee.department ? `${employee.department.name} (${employee.department.code})` : 'Unassigned'}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-400 block">Direct Manager (Reporting Line)</span>
                {employee.manager ? (
                  <span className="font-medium text-slate-900 block mt-0.5">
                    {employee.manager.first_name} {employee.manager.last_name} ({employee.manager.employee_code})
                  </span>
                ) : (
                  <span className="text-slate-400 italic block mt-0.5">No direct manager assigned</span>
                )}
              </div>
              <div>
                <span className="text-xs text-slate-400 block">HR Representative</span>
                {employee.hr_rep ? (
                  <span className="font-medium text-slate-900 block mt-0.5">
                    {employee.hr_rep.first_name} {employee.hr_rep.last_name} ({employee.hr_rep.employee_code})
                  </span>
                ) : (
                  <span className="text-slate-400 italic block mt-0.5">No designated HR representative</span>
                )}
              </div>
            </div>
          </div>

          {/* Card 3: Schedules & Dates */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-600" />
              Work Schedule & Timeline
            </h2>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-xs text-slate-400 block">Joining Date (Hire Date)</span>
                <span className="font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
                  <Calendar className="w-4 h-4 text-slate-400" />
                  {employee.hire_date}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-400 block">Work Schedule Policy</span>
                <span className="font-medium text-slate-900 block mt-0.5">
                  {employee.work_schedule
                    ? `${employee.work_schedule.name} (${employee.work_schedule.shift_start_time} - ${employee.work_schedule.shift_end_time})`
                    : 'Standard System Schedule'}
                </span>
              </div>
              {employee.termination_date && (
                <div>
                  <span className="text-xs text-slate-400 block">Termination Date</span>
                  <span className="font-medium text-rose-700 block mt-0.5">{employee.termination_date}</span>
                </div>
              )}
            </div>
          </div>

          {/* Card 4: Security & Compliance */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h2 className="text-sm font-bold text-slate-900 border-b border-slate-100 pb-3 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-blue-600" />
              Security & Audit Trail
            </h2>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-xs text-slate-400 block">Personnel Record Created</span>
                <span className="font-medium text-slate-700 block mt-0.5">
                  {new Date(employee.created_at).toLocaleString()}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-400 block">Last Profile Update</span>
                <span className="font-medium text-slate-700 block mt-0.5">
                  {new Date(employee.updated_at).toLocaleString()}
                </span>
              </div>
              <div>
                <span className="text-xs text-slate-400 block">Active Status</span>
                <span className="font-medium text-slate-900 flex items-center gap-1.5 mt-0.5">
                  {employee.is_active ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-600" />
                  )}
                  {employee.is_active ? 'Credentials Enabled' : 'Sessions Terminated / Access Blocked'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

