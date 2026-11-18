'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiClient, AuthUser } from '@/lib/api-client';

/** Roles that may use the web portal. Employees use the desktop app only. */
export type UserRole = 'ADMIN' | 'HR' | 'MANAGER';

export interface AuthUserInfo {
  id: string;
  email: string;
  role: string;
  display_name: string;
  is_superuser?: boolean;
}

interface RoleContextType {
  /** Portal role of the signed-in account (null while signed out). */
  role: UserRole | null;
  roleLabel: string;
  user: AuthUserInfo | null;
  isAuthenticated: boolean;
  /** False until the saved session has been read from storage. */
  ready: boolean;
  sessionMessage: string | null;
  loginUser: (user: AuthUser) => void;
  logoutUser: (message?: string) => Promise<void>;
}

const RoleContext = createContext<RoleContextType>({
  role: null,
  roleLabel: '',
  user: null,
  isAuthenticated: false,
  ready: false,
  sessionMessage: null,
  loginUser: () => {},
  logoutUser: async () => {},
});

const ROLE_LABELS: Record<UserRole, string> = {
  ADMIN: 'Administrator',
  HR: 'HR',
  MANAGER: 'Manager',
};

const USER_KEY = 'portal_user';

export function normalizeRole(roleName?: string, isSuperuser?: boolean): UserRole | null {
  if (isSuperuser) return 'ADMIN';
  const lower = (roleName || '').trim().toLowerCase();
  if (lower.includes('admin')) return 'ADMIN';
  if (lower.includes('hr') || lower === 'human resources') return 'HR';
  if (lower.includes('manager') || lower.includes('lead') || lower.includes('supervisor')) return 'MANAGER';
  return null;
}

function toUserInfo(user: AuthUser): AuthUserInfo {
  const local = user.email.split('@')[0];
  return {
    id: user.id,
    email: user.email,
    role: user.role,
    display_name: local.charAt(0).toUpperCase() + local.slice(1),
    is_superuser: user.is_superuser,
  };
}

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUserInfo | null>(null);
  const [ready, setReady] = useState(false);
  const [sessionMessage, setSessionMessage] = useState<string | null>(null);

  const clearLocal = useCallback((message?: string) => {
    apiClient.clearSession();
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem('portal_role');
    setUser(null);
    setSessionMessage(message ?? null);
  }, []);

  useEffect(() => {
    apiClient.onSessionExpired(() => clearLocal('Your session expired. Please sign in again.'));

    const token = apiClient.getToken();
    const saved = localStorage.getItem(USER_KEY);
    if (token && saved) {
      try {
        setUser(JSON.parse(saved) as AuthUserInfo);
      } catch {
        clearLocal();
      }
      // Re-check the account with the server: the role may have changed or the account been disabled.
      apiClient
        .getCurrentUser()
        .then((me) => {
          if (!normalizeRole(me.role, me.is_superuser)) {
            clearLocal('Employee accounts sign in with the desktop app, not the web portal.');
            return;
          }
          const info = toUserInfo(me);
          localStorage.setItem(USER_KEY, JSON.stringify(info));
          setUser(info);
        })
        .catch((err: unknown) => {
          const status = (err as { status?: number; statusCode?: number })?.status
            ?? (err as { statusCode?: number })?.statusCode;
          const message = err instanceof Error ? err.message : String(err ?? '');
          // Clear stale UI for auth failures; keep session only for offline/5xx.
          if (status === 401 || status === 403 || /401|403|unauthorized|forbidden|disabled/i.test(message)) {
            clearLocal(status === 403 ? 'This account is no longer allowed to use the portal.' : undefined);
          }
        });
    } else if (token || saved) {
      clearLocal();
    }
    setReady(true);
    return () => apiClient.onSessionExpired(null);
  }, [clearLocal]);

  const loginUser = useCallback((authUser: AuthUser) => {
    const info = toUserInfo(authUser);
    localStorage.setItem(USER_KEY, JSON.stringify(info));
    setSessionMessage(null);
    setUser(info);
  }, []);

  const logoutUser = useCallback(
    async (message?: string) => {
      await apiClient.logout();
      clearLocal(message);
    },
    [clearLocal]
  );

  const role = user ? normalizeRole(user.role, user.is_superuser) : null;

  return (
    <RoleContext.Provider
      value={{
        role,
        roleLabel: role ? ROLE_LABELS[role] : '',
        user,
        isAuthenticated: user !== null && role !== null,
        ready,
        sessionMessage,
        loginUser,
        logoutUser,
      }}
    >
      {children}
    </RoleContext.Provider>
  );
};

export const useRole = () => useContext(RoleContext);
