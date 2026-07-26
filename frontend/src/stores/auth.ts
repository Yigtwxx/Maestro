// Auth session store (Zustand). Tokens live in localStorage (see api.ts);
// this store tracks derived auth state + the current user profile for the UI.

import { create } from 'zustand';
import { api, tokenStore } from '@/lib/api';
import { useTaskStore } from '@/stores/tasks';
import type { MfaChallenge, UserPublic } from '@/types';

interface AuthState {
  isAuthenticated: boolean;
  hydrated: boolean;
  email: string | undefined;
  user: UserPublic | undefined;
  hydrate: () => void;
  refreshUser: () => Promise<void>;
  setUser: (user: UserPublic) => void;
  /** Resolves to an MFA challenge when 2FA is on (login not yet complete). */
  login: (email: string, password: string) => Promise<MfaChallenge | undefined>;
  completeMfa: (mfaToken: string, code: string, email: string) => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  hydrated: false,
  email: undefined,
  user: undefined,

  hydrate: () => {
    const authenticated = Boolean(tokenStore.getAccess());
    set({ isAuthenticated: authenticated, hydrated: true });
    if (authenticated) void get().refreshUser();
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

  logout: () => {
    tokenStore.clear();
    // Drop the previous session's task view (and close its socket) so it never
    // shows up for whoever logs in next.
    useTaskStore.getState().reset();
    set({ isAuthenticated: false, email: undefined, user: undefined });
  },
}));
