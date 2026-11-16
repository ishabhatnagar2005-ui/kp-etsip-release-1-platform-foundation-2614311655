import type { LoginResponse, User } from './types';

const base = import.meta.env.VITE_API_BASE_URL ?? '';
const key = 'etsip_token';
export const getToken = () => sessionStorage.getItem(key);
export const clearToken = () => sessionStorage.removeItem(key);

async function request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = getToken();
  const response = await fetch(`${base}/api/auth${path}`, {
    method,
    headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') clearToken();
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please try again.');
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export async function signIn(email: string, password: string): Promise<User> {
  const result = await request<LoginResponse>('/login', 'POST', { email, password });
  sessionStorage.setItem(key, result.token);
  return result.user;
}
export const getMe = () => request<User>('/me');
export const saveProfile = (defaultLandingPage: User['defaultLandingPage']) => request<User>('/profile', 'PUT', { defaultLandingPage });
export const changePassword = (currentPassword: string, newPassword: string) => request<void>('/password', 'PUT', { currentPassword, newPassword });
export async function signOut() { try { await request<void>('/logout', 'POST'); } finally { clearToken(); } }
