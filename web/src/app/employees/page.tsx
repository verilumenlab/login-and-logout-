'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Users,
  UserPlus,
  Upload,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Building2,
  Calendar,
  Briefcase,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  ShieldAlert,
  Loader2,
  Trash2,
} from 'lucide-react';
import { apiClient, Department, Employee, EmployeeCreate, EmployeeImportResult } from '@/lib/api-client';

export default function EmployeesPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filtering State
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedDept, setSelectedDept] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  // Form State
  const [formData, setFormData] = useState<EmployeeCreate>({
    first_name: '',
    last_name: '',
    email: '',
    employee_code: '',
    phone: '',
    job_title: '',
    department_id: '',
    manager_id: '',
    hr_rep_id: '',
    hire_date: new Date().toISOString().split('T')[0],
    initial_password: 'WelcomeTitan123!',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Import State
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<EmployeeImportResult | null>(null);

  const fetchEmployees = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.listEmployees({
        search: searchTerm || undefined,
        department_id: selectedDept || undefined,
        employment_status: selectedStatus || undefined,
        page,
        page_size: pageSize,
      });
      setEmployees(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err: any) {
      setError(err.message || 'Failed to load employees');
    } finally {
      setLoading(false);
    }
  };

  const fetchDepartments = async () => {
    try {
      const depts = await apiClient.listDepartments();
      setDepartments(depts);
    } catch (err) {
      console.error('Failed to load departments', err);
    }
  };

  useEffect(() => {
    fetchDepartments();
  }, []);

  useEffect(() => {
    fetchEmployees();
  }, [page, selectedDept, selectedStatus]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchEmployees();
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (!formData.first_name.trim()) errors.first_name = 'First name is required.';
    if (!formData.last_name.trim()) errors.last_name = 'Last name is required.';
    if (!formData.email.trim()) {
      errors.email = 'Email is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      errors.email = 'Enter a valid corporate email address.';
    }
    if (!formData.employee_code.trim()) {
      errors.employee_code = 'Employee code/ID is required.';
    } else if (formData.employee_code.trim().length < 2) {
      errors.employee_code = 'Employee code must be at least 2 characters.';
    }
    if (!formData.hire_date) errors.hire_date = 'Hire date is required.';

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreateEmployee = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setActionLoading(true);
    setError(null);
    try {
      await apiClient.createEmployee({
        ...formData,
        department_id: formData.department_id || undefined,
        manager_id: formData.manager_id || undefined,
        hr_rep_id: formData.hr_rep_id || undefined,
      });
      setShowAddModal(false);
      setFormData({
        first_name: '',
        last_name: '',
        email: '',
        employee_code: '',
        phone: '',
        job_title: '',
        department_id: '',
        manager_id: '',
        hr_rep_id: '',
        hire_date: new Date().toISOString().split('T')[0],
        initial_password: 'WelcomeTitan123!',
      });
      fetchEmployees();
    } catch (err: any) {
      setError(err.message || 'Failed to create employee');
    } finally {
      setActionLoading(false);
    }
  };

  const handleToggleStatus = async (emp: Employee) => {
    const newStatus = !emp.is_active;
    if (confirm(`Are you sure you want to ${newStatus ? 'activate' : 'deactivate'} ${emp.full_name}?`)) {
      try {
        await apiClient.toggleEmployeeStatus(emp.id, newStatus);
        fetchEmployees();
      } catch (err: any) {
        alert(err.message || 'Failed to update status');
      }
    }
  };

  const handleDeleteEmployee = async (emp: Employee) => {
    if (
      confirm(
        `Are you sure you want to permanently delete employee account for ${emp.full_name} (${emp.employee_code})?\n\nThis action cannot be undone and will delete their user account, credentials, and profile.`
      )
    ) {
      setActionLoading(true);
      try {
        await apiClient.deleteEmployee(emp.id);
        fetchEmployees();
      } catch (err: any) {
        setError(err.message || 'Failed to delete employee account');
      } finally {
        setActionLoading(false);
      }
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importFile) return;

    setActionLoading(true);
    setImportResult(null);
    try {
      const data = new FormData();
      data.append('file', importFile);
      const res = await apiClient.importEmployees(data);
      setImportResult(res);
      if (res.success_count > 0) {
        fetchEmployees();
      }
    } catch (err: any) {
      setError(err.message || 'Import failed');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <Users className="w-7 h-7 text-blue-600" />
            Employee Management
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Personnel directory, role assignments, department mappings, and bulk ingestion.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setImportResult(null);
              setImportFile(null);
              setShowImportModal(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 shadow-sm transition"
          >
            <Upload className="w-4 h-4 text-slate-500" />
            Import CSV / Excel
          </button>
          <button
            onClick={() => {
              setFormErrors({});
              setShowAddModal(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm transition"
          >
            <UserPlus className="w-4 h-4" />
            Add Employee
          </button>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 rounded-xl flex items-center justify-between gap-3 animate-fadeIn">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />
            <div>
              <div className="text-sm text-red-700 dark:text-red-300 font-medium">{error}</div>
              {error.toLowerCase().includes('credential') && (
                <div className="text-xs text-red-600 dark:text-red-400 mt-0.5">
                  Your session may have expired or you are not signed in. Please sign in as an Administrator or HR to manage personnel.
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {error.toLowerCase().includes('credential') && (
              <Link
                href="/login"
                className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-lg shadow-sm transition"
              >
                Sign In Now
              </Link>
            )}
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 dark:hover:text-red-300 p-1 text-lg">
              &times;
            </button>
          </div>
        </div>
      )}

      {/* Search and Filters Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4">
        <form onSubmit={handleSearch} className="flex-1 flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name, employee code, email, or job title..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <button
            type="submit"
            className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-medium rounded-lg transition"
          >
            Search
          </button>
        </form>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-slate-400" />
            <select
              value={selectedDept}
              onChange={(e) => {
                setSelectedDept(e.target.value);
                setPage(1);
              }}
              className="text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Departments</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.code})
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setPage(1);
              }}
              className="text-sm border border-slate-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="ON_LEAVE">On Leave</option>
              <option value="PROBATION">Probation</option>
              <option value="TERMINATED">Terminated</option>
            </select>
          </div>
        </div>
      </div>

      {/* Employees Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center gap-3 text-slate-500">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            <p className="text-sm font-medium">Loading personnel directory...</p>
          </div>
        ) : employees.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            <Users className="w-12 h-12 mx-auto text-slate-300 mb-3" />
            <h3 className="text-base font-semibold text-slate-700">No employees found</h3>
            <p className="text-sm text-slate-400 max-w-sm mx-auto mt-1">
              No personnel match your search filters or the organization has no registered employees yet.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-6 py-3">Employee</th>
                  <th className="px-6 py-3">Code / ID</th>
                  <th className="px-6 py-3">Department</th>
                  <th className="px-6 py-3">Reporting Line</th>
                  <th className="px-6 py-3">Joining Date</th>
                  <th className="px-6 py-3">Account Status</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {employees.map((emp) => (
                  <tr key={emp.id} className="hover:bg-slate-50/75 transition">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-700 font-bold flex items-center justify-center text-sm">
                          {emp.first_name[0]}
                          {emp.last_name[0]}
                        </div>
                        <div>
                          <div className="font-semibold text-slate-900">{emp.full_name}</div>
                          <div className="text-xs text-slate-400">{emp.email}</div>
                          {emp.job_title && (
                            <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-1">
                              <Briefcase className="w-3 h-3 text-slate-400" />
                              {emp.job_title}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-mono text-xs font-semibold bg-slate-100 text-slate-800 px-2 py-1 rounded">
                        {emp.employee_code}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {emp.department ? (
                        <div className="text-slate-800 font-medium text-xs">
                          {emp.department.name}
                          <span className="text-slate-400 block text-[11px]">{emp.department.code}</span>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">Unassigned</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {emp.manager ? (
                        <div className="text-xs text-slate-700">
                          <span className="font-medium text-slate-900">
                            {emp.manager.first_name} {emp.manager.last_name}
                          </span>
                          <span className="block text-[11px] text-slate-400">({emp.manager.employee_code})</span>
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400 italic">No manager</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-600">
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        {emp.hire_date}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full w-fit ${
                            emp.is_active
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-rose-50 text-rose-700 border border-rose-200'
                          }`}
                        >
                          {emp.is_active ? (
                            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          ) : (
                            <XCircle className="w-3 h-3 text-rose-600" />
                          )}
                          {emp.is_active ? 'Active' : 'Inactive'}
                        </span>
                        {emp.employment_status !== 'ACTIVE' && (
                          <span className="text-[10px] uppercase font-bold text-slate-400">
                            {emp.employment_status}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleToggleStatus(emp)}
                          className={`text-xs px-2.5 py-1 rounded font-medium transition ${
                            emp.is_active
                              ? 'text-rose-600 hover:bg-rose-50'
                              : 'text-emerald-600 hover:bg-emerald-50'
                          }`}
                        >
                          {emp.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <Link
                          href={`/employees/${emp.id}`}
                          className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:bg-blue-50 dark:hover:bg-blue-950/40 px-2.5 py-1 rounded font-medium transition"
                        >
                          View Profile
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                        <button
                          onClick={() => handleDeleteEmployee(emp)}
                          className="inline-flex items-center gap-1 text-xs text-rose-600 hover:text-rose-800 hover:bg-rose-50 dark:hover:bg-rose-950/40 px-2.5 py-1 rounded font-medium transition"
                          title="Permanently delete employee account"
                        >
                          <Trash2 className="w-3 h-3" />
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {total > 0 && (
          <div className="px-6 py-4 border-t border-slate-200 bg-slate-50/50 flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing <span className="font-semibold text-slate-700">{(page - 1) * pageSize + 1}</span> to{' '}
              <span className="font-semibold text-slate-700">{Math.min(page * pageSize, total)}</span> of{' '}
              <span className="font-semibold text-slate-700">{total}</span> employees
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 border border-slate-300 rounded bg-white text-slate-700 disabled:opacity-50 hover:bg-slate-50 flex items-center gap-1 transition"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                Previous
              </button>
              <span className="text-slate-600 font-medium">
                Page {page} of {totalPages}
              </span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 border border-slate-300 rounded bg-white text-slate-700 disabled:opacity-50 hover:bg-slate-50 flex items-center gap-1 transition"
              >
                Next
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add Employee Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-blue-600" />
                Add New Employee
              </h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600 text-xl font-bold"
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateEmployee} className="p-6 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">First Name *</label>
                  <input
                    type="text"
                    required
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {formErrors.first_name && (
                    <p className="text-xs text-red-500 mt-1">{formErrors.first_name}</p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Last Name *</label>
                  <input
                    type="text"
                    required
                    value={formData.last_name}
                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {formErrors.last_name && (
                    <p className="text-xs text-red-500 mt-1">{formErrors.last_name}</p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Email Address *</label>
                  <input
                    type="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {formErrors.email && (
                    <p className="text-xs text-red-500 mt-1">{formErrors.email}</p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Employee Code / ID *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. EMP-1002"
                    value={formData.employee_code}
                    onChange={(e) => setFormData({ ...formData, employee_code: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase font-mono"
                  />
                  {formErrors.employee_code && (
                    <p className="text-xs text-red-500 mt-1">{formErrors.employee_code}</p>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Job Title</label>
                  <input
                    type="text"
                    placeholder="e.g. Senior Software Engineer"
                    value={formData.job_title || ''}
                    onChange={(e) => setFormData({ ...formData, job_title: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Phone Number</label>
                  <input
                    type="text"
                    placeholder="e.g. +1-555-0100"
                    value={formData.phone || ''}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Department</label>
                  <select
                    value={formData.department_id || ''}
                    onChange={(e) => setFormData({ ...formData, department_id: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select Department</option>
                    {departments.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} ({d.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Direct Manager</label>
                  <select
                    value={formData.manager_id || ''}
                    onChange={(e) => setFormData({ ...formData, manager_id: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">No Manager</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.full_name} ({emp.employee_code})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">HR Representative</label>
                  <select
                    value={formData.hr_rep_id || ''}
                    onChange={(e) => setFormData({ ...formData, hr_rep_id: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Select HR Rep</option>
                    {employees.map((emp) => (
                      <option key={emp.id} value={emp.id}>
                        {emp.full_name} ({emp.employee_code})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Joining / Hire Date *</label>
                  <input
                    type="date"
                    required
                    value={formData.hire_date}
                    onChange={(e) => setFormData({ ...formData, hire_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {formErrors.hire_date && (
                    <p className="text-xs text-red-500 mt-1">{formErrors.hire_date}</p>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Initial Account Password
                  </label>
                  <input
                    type="password"
                    placeholder="Min 8 characters"
                    value={formData.initial_password || ''}
                    onChange={(e) => setFormData({ ...formData, initial_password: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="pt-4 border-t border-slate-200 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm transition disabled:opacity-50 flex items-center gap-2"
                >
                  {actionLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                  Save Employee Record
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Bulk Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-xl w-full">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Upload className="w-5 h-5 text-blue-600" />
                Bulk Import Employees (.CSV or .XLSX)
              </h2>
              <button
                onClick={() => setShowImportModal(false)}
                className="text-slate-400 hover:text-slate-600 text-xl font-bold"
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleImportSubmit} className="p-6 space-y-4">
              <p className="text-xs text-slate-500 leading-relaxed">
                Upload an Excel spreadsheet (.xlsx) or CSV file containing employee records. Required headers:
                <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded font-mono ml-1">
                  first_name, last_name, email, employee_code, hire_date
                </code>
                . Optional headers:
                <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded font-mono ml-1">
                  job_title, phone, department_code, manager_code
                </code>
                .
              </p>

              <div className="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center hover:border-blue-400 transition">
                <input
                  type="file"
                  accept=".csv,.xlsx"
                  required
                  onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                  className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
                />
              </div>

              {importResult && (
                <div className="space-y-3">
                  <div className="flex items-center gap-4 text-sm font-semibold">
                    <span className="text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
                      ✓ Imported: {importResult.success_count}
                    </span>
                    {importResult.error_count > 0 && (
                      <span className="text-rose-700 bg-rose-50 px-2.5 py-1 rounded-full border border-rose-200">
                        ✕ Errors: {importResult.error_count}
                      </span>
                    )}
                  </div>
                  {importResult.errors.length > 0 && (
                    <div className="max-h-40 overflow-y-auto bg-rose-50/50 p-3 rounded-lg border border-rose-200 text-xs text-rose-800 space-y-1">
                      {importResult.errors.map((err, i) => (
                        <div key={i}>
                          <span className="font-bold">Row {err.row}</span> ({err.employee_code || err.email}):{' '}
                          {err.errors.join(', ')}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="pt-4 border-t border-slate-200 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !importFile}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium shadow-sm transition disabled:opacity-50 flex items-center gap-2"
                >
                  {actionLoading && <Loader2 className="w-4 h-4 animate-spin" />}
                  Start Ingestion
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

