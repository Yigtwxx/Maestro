// First-run onboarding store (Zustand). Persisted to localStorage under
// ONBOARDING_KEY. Modeled on the consent store: a hand-rolled read/write with a
// `hydrated` guard so the coachmark never renders before localStorage is read
// (which would flash the tour at users who already finished it and mismatch SSR).
//
// There is no backend "onboarded" flag by design. A user with no stored record
// is treated as `active` from step 0 -- so both a freshly registered user and an
// existing user who has never seen the tour get it exactly once. Completing or
// skipping it writes a terminal status that never reopens.

import { create } from 'zustand';
import { ONBOARDING_KEY } from '@/lib/constants';

type OnboardingStatus = 'active' | 'done' | 'skipped';

interface OnboardingRecord {
  /** `active` while the tour runs; `done`/`skipped` are terminal. */
  status: OnboardingStatus;
  /** Index into the resolved (skip-filtered) step list the user is on. */
  stepIndex: number;
}

interface OnboardingState extends OnboardingRecord {
  /** False until localStorage has been read; the coachmark must not render before. */
  hydrated: boolean;
  hydrate: () => void;
  /** Advance one step; the overlay calls `complete()` itself past the last step. */
  next: () => void;
  /** Restart the tour from the beginning (e.g. a "replay onboarding" control). */
  start: () => void;
  complete: () => void;
  skip: () => void;
}

const DEFAULT: OnboardingRecord = { status: 'active', stepIndex: 0 };

function read(): OnboardingRecord {
  if (typeof window === 'undefined') return DEFAULT;
  try {
    const raw = window.localStorage.getItem(ONBOARDING_KEY);
    if (raw === null) return DEFAULT;
    const parsed = JSON.parse(raw) as Partial<OnboardingRecord>;
    const status: OnboardingStatus =
      parsed.status === 'done' || parsed.status === 'skipped' ? parsed.status : 'active';
    const stepIndex =
      typeof parsed.stepIndex === 'number' && parsed.stepIndex >= 0 ? parsed.stepIndex : 0;
    return { status, stepIndex };
  } catch {
    // Corrupt or unreadable storage means "never onboarded", so show the tour.
    return DEFAULT;
  }
}

function write(record: OnboardingRecord): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(ONBOARDING_KEY, JSON.stringify(record));
  } catch {
    // Private mode or a full quota: the tour reappears next visit. Harmless.
  }
}

export const useOnboardingStore = create<OnboardingState>((set, get) => ({
  ...DEFAULT,
  hydrated: false,

  hydrate: () => {
    set({ ...read(), hydrated: true });
  },

  next: () => {
    const record: OnboardingRecord = { status: 'active', stepIndex: get().stepIndex + 1 };
    write(record);
    set(record);
  },

  start: () => {
    write(DEFAULT);
    set(DEFAULT);
  },

  complete: () => {
    const record: OnboardingRecord = { status: 'done', stepIndex: get().stepIndex };
    write(record);
    set(record);
  },

  skip: () => {
    const record: OnboardingRecord = { status: 'skipped', stepIndex: get().stepIndex };
    write(record);
    set(record);
  },
}));
