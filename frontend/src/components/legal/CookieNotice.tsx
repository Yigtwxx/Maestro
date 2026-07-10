'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { Cookie } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useConsentStore } from '@/stores/consent';

/**
 * A one-time notice, not a consent gate.
 *
 * Sign-in tokens are strictly necessary for a service the user explicitly asked
 * for, which exempts them from consent, and nothing else is stored. So there is
 * no Accept button: accepting implies a refusable alternative that does not
 * exist. If telemetry is ever added, this becomes a real choice -- the consent
 * record already has a slot for it.
 */
export function CookieNotice() {
  const hydrated = useConsentStore((state) => state.hydrated);
  const acknowledgedAt = useConsentStore((state) => state.acknowledgedAt);
  const hydrate = useConsentStore((state) => state.hydrate);
  const acknowledge = useConsentStore((state) => state.acknowledge);

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
          <p className="font-mono text-xs leading-relaxed text-slate-200">
            We store a sign-in token in your browser so you stay logged in. No
            cookies, no analytics, no tracking.{' '}
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
        </div>
      </div>
    </div>
  );
}
