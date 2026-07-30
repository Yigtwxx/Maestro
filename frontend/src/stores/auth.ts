// Auth session store (Zustand). The access token lives in memory and the
// refresh token in an httpOnly cookie (see api.ts); this store tracks derived
// auth state + the current user profile for the UI.

import { create } from 'zustand';
import { accessTokenStore, api, ensureFreshAccessToken } from '@/lib/api';
import { useTaskStore } from '@/stores/tasks';
import type { MfaChallenge, UserPublic } from '@/types';

interface AuthState {
  isAuthenticated: boolean;
  hydrated: boolean;
  email: string | undefined;
  user: UserPublic | undefined;
  hydrate: () => Promise<void>;
  refreshUser: () => Promise<void>;
  setUser: (user: UserPublic) => void;
  /** Resolves to an MFA challenge when 2FA is on (login not yet complete). */
  login: (email: string, password: string) => Promise<MfaChallenge | undefined>;
  completeMfa: (mfaToken: string, code: string, email: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  hydrated: false,
  email: undefined,
  user: undefined,

  // Asynchronous because the access token is held in memory: a reload starts
  // with none, so the only way to learn whether a session survived is to spend
  // the refresh cookie. Callers must keep rendering their loading state until
  // `hydrated` flips — `(app)/layout.tsx` already does, so the login screen
  // cannot flash in between. Guarded against re-entry for StrictMode's
  // double-invoked effect and for remounts.
  hydrate: async () => {
    if (get().hydrated) return;
    const token = await ensureFreshAccessToken();
    set({ isAuthenticated: Boolean(token), hydrated: true });
    if (token) void get().refreshUser();
  },

  refreshUser: async () => {
    try {
      const user = await api.getCurrentUser();
      set({ user, email: user.email });
    } catch {
      // Profile fetch is best-effort; auth gating relies on tokens alone.
    }
  },

  setUser: (user: UserPublic) => {
    set({ user, email: user.email });
  },

  login: async (email: string, password: string) => {
    const result = await api.login(email, password);
    if ('mfa_required' in result) {
      // 2FA gate: tokens are not issued yet. The caller collects the code.
      return result;
    }
    set({ isAuthenticated: true, email });
    void get().refreshUser();
    return undefined;
  },

  completeMfa: async (mfaToken: string, code: string, email: string) => {
    await api.loginVerifyTotp(mfaToken, code);
    // Set email synchronously, mirroring the password login path, so UI reading
    // it right after (header, analytics) doesn't render an empty value while
    // refreshUser is still in flight.
    set({ isAuthenticated: true, email });
    void get().refreshUser();
  },

  logout: async () => {
    // Fire the revocation first (it is `keepalive`, so a navigation cannot
    // cancel it), then clear local state immediately so signing out feels
    // instant. The ordering is not a security question — /auth/logout is
    // authenticated by the cookie, which nothing here can clear, and the access
    // token expires on its own in 30 minutes. What matters is that the
    // server-side family revocation is attempted at all: before this, sign-out
    // was purely local and left the session valid for a further seven days.
    const revoked = api.logout().catch(() => undefined);
    accessTokenStore.clear();
    // Drop the previous session's task view (and close its socket) so it never
    // shows up for whoever logs in next.
    useTaskStore.getState().reset();
    set({ isAuthenticated: false, email: undefined, user: undefined });
    await revoked;
  },
}));
