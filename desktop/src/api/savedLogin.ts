import { deleteSecureToken, getSecureToken, saveSecureToken } from './ipc';

const SAVED_LOGIN_KEY = 'saved_login';

export type SavedLogin = {
  email: string;
  password: string;
};

export async function getSavedLogin(): Promise<SavedLogin | null> {
  const raw = await getSecureToken(SAVED_LOGIN_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<SavedLogin>;
    const email = String(parsed.email || '').trim();
    const password = String(parsed.password || '');
    if (!email || !password) return null;
    return { email, password };
  } catch {
    return null;
  }
}

export async function saveLoginCredentials(email: string, password: string): Promise<void> {
  const payload: SavedLogin = {
    email: email.trim(),
    password,
  };
  await saveSecureToken(SAVED_LOGIN_KEY, JSON.stringify(payload));
}

export async function clearSavedLogin(): Promise<void> {
  await deleteSecureToken(SAVED_LOGIN_KEY);
}
