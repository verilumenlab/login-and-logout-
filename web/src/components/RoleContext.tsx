'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';

export type UserRole = 'ADMIN' | 'HR' | 'MANAGER' | 'EMPLOYEE';

export interface AuthUserInfo {
  id: string;
  email: string;
  role: string;
  full_name?: string;
  is_superuser?: boolean;
}

interface RoleContextType {
  role: UserRole;
  setRole: (role: UserRole) => void;
  roleLabel: string;
  user: AuthUserInfo | null;
  isAuthenticated: boolean;
  loginUser: (token: string, userData: any) => void;
  logoutUser: () => void;
}

const RoleContext = createContext<RoleContextType>({
  role: 'ADMIN',
  setRole: () => {},
  roleLabel: 'Super Admin',
  user: null,
  isAuthenticated: false,
  loginUser: () => {},
  logoutUser: () => {},
});

const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: 'Administrator',
  HR: 'HR Representative',
  MANAGER: 'Department Manager',
  EMPLOYEE: 'Employee (Self-Service)',
};

export function normalizeRole(roleName?: string): UserRole {
  if (!roleName) return 'ADMIN';
  const lower = roleName.toLowerCase();
  if (lower.includes('admin')) return 'ADMIN';
  if (lower.includes('hr')) return 'HR';
  if (lower.includes('manager')) return 'MANAGER';
  return 'EMPLOYEE';
}

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [role, setRoleState] = useState<UserRole>('ADMIN');
  const [user, setUser] = useState<AuthUserInfo | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  useEffect(() => {
    // Check saved session on mount
    const token = apiClient.getToken();
    const savedRole = localStorage.getItem('portal_role') as UserRole | null;
    const savedUser = localStorage.getItem('portal_user');

    if (token) {
      setIsAuthenticated(true);
      apiClient.setToken(token);
    }

    if (savedUser) {
      try {
        const parsed = JSON.parse(savedUser);
        setUser(parsed);
      } catch {
        // ignore
      }
    }

    if (savedRole && ['ADMIN', 'HR', 'MANAGER', 'EMPLOYEE'].includes(savedRole)) {
      setRoleState(savedRole);
    }
  }, []);

  const setRole = (newRole: UserRole) => {
    setRoleState(newRole);
    localStorage.setItem('portal_role', newRole);
  };

  const loginUser = (token: string, userData: any) => {
    apiClient.setToken(token);
    const normalized = normalizeRole(userData.role);
    const info: AuthUserInfo = {
      id: userData.id,
      email: userData.email,
      role: userData.role,
      full_name: userData.full_name || userData.email.split('@')[0],
      is_superuser: userData.is_superuser,
    };
    setUser(info);
    setIsAuthenticated(true);
    setRole(normalized);
    localStorage.setItem('portal_user', JSON.stringify(info));
  };

  const logoutUser = () => {
    apiClient.setToken(null);
    setUser(null);
    setIsAuthenticated(false);
    localStorage.removeItem('auth_token');
    localStorage.removeItem('portal_role');
    localStorage.removeItem('portal_user');
  };

  return (
    <RoleContext.Provider
      value={{
        role,
        setRole,
        roleLabel: ROLE_LABELS[role],
        user,
        isAuthenticated,
        loginUser,
        logoutUser,
      }}
    >
      {children}
    </RoleContext.Provider>
  );
};

export const useRole = () => useContext(RoleContext);
