'use client';

import { useEffect } from 'react';
import { markSentryReady } from '@/lib/observability/reporter';

// Module-level: survives re-mounts and StrictMode double-effects.
let initialized = false;

/**
 * Initializes the browser Sentry SDK on mount. Rendered by the root layout
 * only when a DSN is configured (runtime env read, see
 * `lib/observability/config.ts`), so disabled deployments never download the
 * Sentry chunk at all.
 *
 * Trade-off of init-on-mount: errors thrown before hydration are not captured
 * client-side — but their server render is captured via `onRequestError` in
 * `instrumentation.ts`.
 */
export function SentryInit({
  dsn,
  environment,
}: {
  dsn: string;
  environment: string;
}) {
  useEffect(() => {
    if (initialized) return;
    initialized = true;
    void import('@sentry/nextjs').then((Sentry) => {
      Sentry.init({
        dsn,
        environment,
        tracesSampleRate: 0, // errors only — no APM, protects free-tier quota
        sendDefaultPii: false,
        // No replayIntegration: keeps the lazy chunk small and the PII
        // surface minimal.
      });
      markSentryReady();
    });
  }, [dsn, environment]);
  return null;
}
