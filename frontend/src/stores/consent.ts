// Storage-consent store (Zustand). Persisted to localStorage under
// CONSENT_KEY. See the Cookie Policy: `necessary` is not a choice (sign-in
// tokens are exempt from consent), while `analytics` is a real one on
// deployments that enable Umami -- asked by the cookie notice, changeable any
// time on /cookies. It defaults to false, which is what "we never asked, so we
// never assumed" has to mean, and nothing reads it as true without an explicit
// decide() call.

import { create } from 'zustand';
import { CONSENT_KEY } from '@/lib/constants';

interface ConsentRecord {
  /** Sign-in tokens. Exempt from consent; recorded for completeness. */
  necessary: true;
  /**
   * Self-hosted analytics (Umami) on the marketing pages. Set by the consent
   * banner or the /cookies page on deployments that configure a website id;
   * stays false everywhere else.
   */
  analytics: boolean;
  /** ISO timestamp of when the user dismissed the notice, if they have. */
  acknowledgedAt?: string;
}

interface ConsentState extends ConsentRecord {
  /** False until localStorage has been read; the notice must not render before. */
  hydrated: boolean;
  hydrate: () => void;
  acknowledge: () => void;
  decide: (analytics: boolean) => void;
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

  // An explicit analytics decision: Accept/Reject on the banner, or a change
  // of mind on /cookies. Also acknowledges, so the banner never re-asks.
  decide: (analytics: boolean) => {
    const record: ConsentRecord = {
      necessary: true,
      analytics,
      acknowledgedAt: new Date().toISOString(),
    };
    write(record);
    set(record);
  },
}));
