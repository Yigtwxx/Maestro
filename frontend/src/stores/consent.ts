// Storage-consent store (Zustand). Persisted to localStorage under
// CONSENT_KEY. See the Cookie Policy: today the platform stores nothing that
// isn't strictly necessary, so `necessary` is not a choice and there is nothing
// to reject. `analytics` exists so that adding telemetry later is a change of
// component, not a change of data shape -- and it defaults to false, which is
// what "we never asked, so we never assumed" has to mean.

import { create } from 'zustand';
import { CONSENT_KEY } from '@/lib/constants';

interface ConsentRecord {
  /** Sign-in tokens. Exempt from consent; recorded for completeness. */
  necessary: true;
  /** Product telemetry. Nothing sets this yet; opt-in when something does. */
  analytics: boolean;
  /** ISO timestamp of when the user dismissed the notice, if they have. */
  acknowledgedAt?: string;
}

interface ConsentState extends ConsentRecord {
  /** False until localStorage has been read; the notice must not render before. */
  hydrated: boolean;
  hydrate: () => void;
  acknowledge: () => void;
}

const DEFAULT: ConsentRecord = { necessary: true, analytics: false };

function read(): ConsentRecord {
  if (typeof window === 'undefined') return DEFAULT;
  try {
    const raw = window.localStorage.getItem(CONSENT_KEY);
    if (raw === null) return DEFAULT;
    const parsed = JSON.parse(raw) as Partial<ConsentRecord>;
    return {
      necessary: true,
      analytics: parsed.analytics === true,
      acknowledgedAt: parsed.acknowledgedAt,
    };
  } catch {
    // Corrupt or unreadable storage means "not asked yet", never "consented".
    return DEFAULT;
  }
}

function write(record: ConsentRecord): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CONSENT_KEY, JSON.stringify(record));
  } catch {
    // Private mode or a full quota: the notice reappears next visit. Harmless.
  }
}

export const useConsentStore = create<ConsentState>((set, get) => ({
  ...DEFAULT,
  hydrated: false,

  hydrate: () => {
    set({ ...read(), hydrated: true });
  },

  acknowledge: () => {
    const record: ConsentRecord = {
      necessary: true,
      analytics: get().analytics,
      acknowledgedAt: new Date().toISOString(),
    };
    write(record);
    set(record);
  },
}));
