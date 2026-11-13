'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Building2,
  Plus,
  Edit2,
  Trash2,
  Users,
  Search,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  ShieldAlert,
  ArrowRight,
} from 'lucide-react';
import { apiClient, Department, DepartmentCreate, DepartmentUpdate } from '@/lib/api-client';

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<Department[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Search & Filter
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all');

  // Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingDept, setEditingDept] = useState<Department | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Form State
  const [createForm, setCreateForm] = useState<DepartmentCreate>({
    name: '',
    code: '',
    parent_id: null,
    is_active: true,
  });
  const [editForm, setEditForm] = useState<DepartmentUpdate>({
    name: '',
    code: '',
    is_active: true,
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  const fetchDepartments = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.listDepartments();
      setDepartments(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load departments';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDepartments();
  }, []);

  const showNotification = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 4000);
  };

  // Validation
  const validateCreate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!createForm.name.trim()) errs.name = 'Department name is required';
    if (!createForm.code.trim()) errs.code = 'Department code is required';
    else if (!/^[A-Za-z0-9_-]{2,20}$/.test(createForm.code.trim())) {
      errs.code = 'Code must be 2-20 alphanumeric characters (or - _)';
    }
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const validateEdit = (): boolean => {
    const errs: Record<string, string> = {};
    if (!editForm.name?.trim()) errs.name = 'Department name is required';
    if (!editForm.code?.trim()) errs.code = 'Department code is required';
    else if (!/^[A-Za-z0-9_-]{2,20}$/.test(editForm.code.trim())) {
      errs.code = 'Code must be 2-20 alphanumeric characters (or - _)';
    }
    setFormErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateCreate()) return;

    try {
      setActionLoading(true);
      setError(null);
      await apiClient.createDepartment({
        ...createForm,
        code: createForm.code.trim().toUpperCase(),
        name: createForm.name.trim(),
      });
      setShowCreateModal(false);
      setCreateForm({ name: '', code: '', parent_id: null, is_active: true });
      showNotification('Department created successfully.');
      await fetchDepartments();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create department';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleEditClick = (dept: Department) => {
    setEditingDept(dept);
    setEditForm({
      name: dept.name,
      code: dept.code,
      is_active: dept.is_active,
    });
    setFormErrors({});
    setShowEditModal(true);
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingDept || !validateEdit()) return;

    try {
      setActionLoading(true);
      setError(null);
      await apiClient.updateDepartment(editingDept.id, {
        ...editForm,
        code: editForm.code?.trim().toUpperCase(),
        name: editForm.name?.trim(),
      });
      setShowEditModal(false);
      setEditingDept(null);
      showNotification('Department updated successfully.');
      await fetchDepartments();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update department';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async (dept: Department) => {
    const promptMsg = dept.employee_count > 0
      ? `Department "${dept.name}" has ${dept.employee_count} assigned employee(s). It will be deactivated instead of deleted. Proceed?`
      : `Are you sure you want to delete department "${dept.name}" (${dept.code})?`;

    if (!confirm(promptMsg)) return;

    try {
      setActionLoading(true);
      setError(null);
      const res = await apiClient.deleteDepartment(dept.id);
      showNotification(res.message);
      await fetchDepartments();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete department';
      setError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Filtered List
  const filteredDepartments = departments.filter((d) => {
    const matchesSearch =
      d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      d.code.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus =
      statusFilter === 'all' ||
      (statusFilter === 'active' && d.is_active) ||
      (statusFilter === 'inactive' && !d.is_active);
    return matchesSearch && matchesStatus;
  });

  const totalEmployees = departments.reduce((acc, d) => acc + (d.employee_count || 0), 0);
  const activeCount = departments.filter((d) => d.is_active).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <Building2 className="w-7 h-7 text-indigo-600" />
            Department Management
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Configure enterprise organizational units, business division codes, and team assignments.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/employees"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors shadow-sm"
          >
            <Users className="w-4 h-4 text-slate-500" />
            View Employees
            <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
          </Link>
          <button
            onClick={() => {
              setFormErrors({});
              setShowCreateModal(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            New Department
          </button>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Departments</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{departments.length}</p>
          </div>
          <div className="p-3 bg-indigo-50 text-indigo-600 rounded-xl">
            <Building2 className="w-6 h-6" />
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Units</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">{activeCount}</p>
          </div>
          <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl">
            <CheckCircle2 className="w-6 h-6" />
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Assigned Workforce</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{totalEmployees}</p>
          </div>
          <div className="p-3 bg-blue-50 text-blue-600 rounded-xl">
            <Users className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-red-900">Operation Error</h4>
            <p className="text-sm text-red-700 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {successMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-emerald-900">Success</h4>
            <p className="text-sm text-emerald-700 mt-0.5">{successMessage}</p>
          </div>
        </div>
      )}

      {/* Search & Filter Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by department name or code..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'inactive')}
            className="px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white"
          >
            <option value="all">All Statuses</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>
      </div>

      {/* Department Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-slate-500">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-600 mb-3" />
            <p className="text-sm">Loading enterprise organizational units...</p>
          </div>
        ) : filteredDepartments.length === 0 ? (
          <div className="py-16 text-center">
            <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-slate-800">No departments found</h3>
            <p className="text-sm text-slate-500 mt-1 max-w-sm mx-auto">
              {searchTerm || statusFilter !== 'all'
                ? 'Try adjusting your search query or filter criteria.'
                : 'Get started by creating your first organizational department.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold text-xs uppercase tracking-wider">
                  <th className="py-3 px-4">Department</th>
                  <th className="py-3 px-4">Code</th>
                  <th className="py-3 px-4 text-center">Assigned Members</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4">Created</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDepartments.map((dept) => (
                  <tr key={dept.id} className="hover:bg-slate-50/75 transition-colors">
                    <td className="py-3 px-4 font-medium text-slate-900">
                      <div className="flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-slate-400" />
                        <span>{dept.name}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono text-xs font-semibold text-indigo-600">
                      <span className="px-2 py-0.5 bg-indigo-50 rounded border border-indigo-200/60">
                        {dept.code}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      <Link
                        href={`/employees?department_id=${dept.id}`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 rounded-full text-xs font-medium text-slate-700 transition-colors"
                        title="View employees in this department"
                      >
                        <Users className="w-3 h-3 text-slate-400" />
                        {dept.employee_count} {dept.employee_count === 1 ? 'member' : 'members'}
                      </Link>
                    </td>
                    <td className="py-3 px-4 text-center">
                      {dept.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
                          <XCircle className="w-3 h-3 text-rose-500" />
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-500 text-xs">
                      {new Date(dept.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button
                          onClick={() => handleEditClick(dept)}
                          className="p-1.5 text-slate-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                          title="Edit department"
                        >
                          <Edit2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(dept)}
                          className="p-1.5 text-slate-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title={dept.employee_count > 0 ? 'Deactivate department' : 'Delete department'}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Department Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-fadeIn">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-indigo-600" />
                Create New Department
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none p-1"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Department Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Engineering & Technology"
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                    formErrors.name ? 'border-red-300 bg-red-50/30' : 'border-slate-300'
                  }`}
                />
                {formErrors.name && <p className="text-xs text-red-600 mt-1">{formErrors.name}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Department Code *
                </label>
                <input
                  type="text"
                  placeholder="e.g. ENG, HR, FIN"
                  value={createForm.code}
                  onChange={(e) => setCreateForm({ ...createForm, code: e.target.value.toUpperCase() })}
                  className={`w-full px-3 py-2 text-sm font-mono border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 uppercase ${
                    formErrors.code ? 'border-red-300 bg-red-50/30' : 'border-slate-300'
                  }`}
                />
                {formErrors.code && <p className="text-xs text-red-600 mt-1">{formErrors.code}</p>}
                <p className="text-xs text-slate-400 mt-1">Unique code used for employee identifier routing.</p>
              </div>

              <div className="pt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  id="create_is_active"
                  checked={createForm.is_active}
                  onChange={(e) => setCreateForm({ ...createForm, is_active: e.target.checked })}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="create_is_active" className="text-sm text-slate-700 select-none">
                  Active Department
                </label>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
                >
                  {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  Create Department
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Department Modal */}
      {showEditModal && editingDept && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-fadeIn">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <Edit2 className="w-5 h-5 text-indigo-600" />
                Edit Department
              </h3>
              <button
                onClick={() => setShowEditModal(false)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none p-1"
              >
                &times;
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Department Name *
                </label>
                <input
                  type="text"
                  value={editForm.name || ''}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                    formErrors.name ? 'border-red-300 bg-red-50/30' : 'border-slate-300'
                  }`}
                />
                {formErrors.name && <p className="text-xs text-red-600 mt-1">{formErrors.name}</p>}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Department Code *
                </label>
                <input
                  type="text"
                  value={editForm.code || ''}
                  onChange={(e) => setEditForm({ ...editForm, code: e.target.value.toUpperCase() })}
                  className={`w-full px-3 py-2 text-sm font-mono border rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 uppercase ${
                    formErrors.code ? 'border-red-300 bg-red-50/30' : 'border-slate-300'
                  }`}
                />
                {formErrors.code && <p className="text-xs text-red-600 mt-1">{formErrors.code}</p>}
              </div>

              <div className="pt-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  id="edit_is_active"
                  checked={editForm.is_active ?? true}
                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <label htmlFor="edit_is_active" className="text-sm text-slate-700 select-none">
                  Active Department
                </label>
              </div>

              <div className="pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
                >
                  {actionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

