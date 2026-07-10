// Toast notification store (Zustand). Hand-rolled to match the project's
// dependency-free UI (no toast library). The exported `toast` helper reads the
// store through getState() rather than a hook, so non-component code -- the API
// client, websocket handlers -- can raise notifications too.

import { create } from 'zustand';
import { TOAST_DURATION_MS, TOAST_MAX } from '@/lib/constants';

export type ToastVariant = 'success' | 'error' | 'info';

export interface Toast {
  id: string;
  variant: ToastVariant;
  message: string;
  title?: string;
  duration: number;
}

interface ToastState {
  toasts: Toast[];
  push: (toast: Omit<Toast, 'id' | 'duration'> & { duration?: number }) => void;
  dismiss: (id: string) => void;
}

// A module-level counter, not Math.random/crypto: a deterministic id keeps
// server and client markup identical and pulls in no dependency.
let seq = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  push: ({ duration, ...rest }) => {
    seq += 1;
    const toast: Toast = {
      id: `t${seq}`,
      duration: duration ?? TOAST_DURATION_MS,
      ...rest,
    };
    set((state) => ({
      // Cap the stack so a burst of errors cannot fill the screen; oldest drops.
      toasts: [...state.toasts, toast].slice(-TOAST_MAX),
    }));
  },

  dismiss: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

/**
 * Fire-and-forget helpers usable both in components and outside React. Thin
 * wrappers over the store's `push`; the optional `title` renders a bold heading.
 */
export const toast = {
  success: (message: string, title?: string) =>
    useToastStore.getState().push({ variant: 'success', message, title }),
  error: (message: string, title?: string) =>
    useToastStore.getState().push({ variant: 'error', message, title }),
  info: (message: string, title?: string) =>
    useToastStore.getState().push({ variant: 'info', message, title }),
};
