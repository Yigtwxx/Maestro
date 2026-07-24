'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { Cookie } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useConsentStore } from '@/stores/consent';

/**
 * The storage notice, in one of two shapes depending on the deployment.
 *
 * Without analytics configured (`analyticsAvailable` false) it is a one-time
 * notice, not a consent gate: sign-in tokens are strictly necessary for a
 * service the user explicitly asked for, which exempts them from consent, and
 * nothing else runs. There is no Accept button, because accepting implies a
 * refusable alternative that does not exist.
 *
 * With analytics configured it becomes a real choice: self-hosted Umami wants
 * to count visits on the marketing pages, that is not strictly necessary, so
 * it asks first — with Reject as easy as Accept, per GDPR/KVKK. The script
 * loads only after an explicit yes (see `Analytics`).
 *
 * Either way the notice hides once `acknowledgedAt` is set. Users who
 * dismissed the informational notice before analytics existed are never
 * re-prompted: their record says `analytics: false`, they stay untracked, and
 * /cookies is their path to opt in. Conservative on purpose.
 */
export function CookieNotice({ analyticsAvailable }: { analyticsAvailable: boolean }) {
  const hydrated = useConsentStore((state) => state.hydrated);
  const acknowledgedAt = useConsentStore((state) => state.acknowledgedAt);
  const hydrate = useConsentStore((state) => state.hydrate);
  const acknowledge = useConsentStore((state) => state.acknowledge);
  const decide = useConsentStore((state) => state.decide);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Rendering before localStorage is read would flash the notice at users who
  // already dismissed it, and mismatch the server-rendered markup.
  if (!hydrated || acknowledgedAt !== undefined) return null;

  return (
    <div
      role="region"
      aria-label="Storage notice"
      className="fixed inset-x-3 bottom-3 z-50 sm:inset-x-auto sm:right-4 sm:max-w-md"
    >
      <div className="flex gap-3 rounded-lg border border-border-bright bg-surface/95 p-4 shadow-lg backdrop-blur">
        <Cookie className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          {analyticsAvailable ? (
            <>
              <p className="font-mono text-xs leading-relaxed text-slate-200">
                We store a sign-in token in your browser so you stay logged in.
                On our public pages we would also like to count visits with
                self-hosted, cookieless analytics — anonymous, first-party,
                never sold. Your call.{' '}
                <Link
                  href="/cookies"
                  className="text-accent underline underline-offset-2 hover:text-accent/80"
                >
                  What we store
                </Link>
              </p>
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="ghost" onClick={() => decide(false)}>
                  Reject
                </Button>
                <Button variant="lime" onClick={() => decide(true)}>
                  Accept
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="font-mono text-xs leading-relaxed text-slate-200">
                We store a sign-in token in your browser so you stay logged in.
                No cookies, no analytics, no tracking.{' '}
                <Link
                  href="/cookies"
                  className="text-accent underline underline-offset-2 hover:text-accent/80"
                >
                  What we store
                </Link>
              </p>
              <div className="mt-3 flex justify-end">
                <Button variant="lime" onClick={acknowledge}>
                  Got it
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
