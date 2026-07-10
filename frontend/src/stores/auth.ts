// Auth session store (Zustand). Tokens live in localStorage (see api.ts);
// this store tracks derived auth state + the current user profile for the UI.

import { create } from 'zustand';
import { api, tokenStore } from '@/lib/api';
import { useTaskStore } from '@/stores/tasks';
import type { UserPublic } from '@/types';

interface AuthState {
  isAuthenticated: boolean;
  hydrated: boolean;
  email: string | undefined;
  user: UserPublic | undefined;
  hydrate: () => void;
  refreshUser: () => Promise<void>;
  setUser: (user: UserPublic) => void;
  login: (email: string, password: string) => Promise<void>;
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
    await api.login(email, password);
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
