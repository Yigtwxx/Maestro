'use client';

import { useEffect } from 'react';
import { BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useConsentStore } from '@/stores/consent';

/**
 * The "change your mind later" the Cookie Policy promises, rendered at the
 * bottom of /cookies. Shows the current analytics decision and lets the user
 * flip it — effective immediately, no reload: every pageview is an explicit,
 * consent-gated call (see `Analytics`), so withdrawing consent simply stops
 * the calls.
 *
 * On deployments without analytics configured it says so instead of offering
 * a toggle for something that does not exist.
 */
export function ConsentManager({ analyticsAvailable }: { analyticsAvailable: boolean }) {
  const hydrated = useConsentStore((state) => state.hydrated);
  const analytics = useConsentStore((state) => state.analytics);
  const hydrate = useConsentStore((state) => state.hydrate);
  const decide = useConsentStore((state) => state.decide);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // Same reason as the notice: rendering before localStorage is read would
  // mismatch the server-rendered markup.
  if (!hydrated) return null;

  return (
    <Card className="p-6 sm:p-8">
      <div className="flex gap-3">
        <BarChart3 className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-mono text-sm font-semibold text-white">
            Your analytics choice
          </h2>
          {analyticsAvailable ? (
            <>
              <p className="mt-2 font-mono text-xs leading-relaxed text-slate-200">
                Analytics is currently{' '}
                <span className={analytics ? 'text-primary' : 'text-muted'}>
                  {analytics ? 'on' : 'off'}
                </span>{' '}
                for this browser. It counts visits to our public pages only —
                self-hosted, cookieless, anonymous. Change it any time; the
                change takes effect immediately.
              </p>
              <div className="mt-4 flex justify-end">
                {analytics ? (
                  <Button variant="ghost" onClick={() => decide(false)}>
                    Turn off analytics
                  </Button>
                ) : (
                  <Button variant="lime-outline" onClick={() => decide(true)}>
                    Allow analytics
                  </Button>
                )}
              </div>
            </>
          ) : (
            <p className="mt-2 font-mono text-xs leading-relaxed text-muted">
              Analytics is not enabled on this deployment. There is nothing to
              opt in to.
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
