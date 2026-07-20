/**
 * Client-safe error reporting facade for error boundaries.
 *
 * The module-level flag keeps the Sentry chunk entirely out of the network
 * when tracking is disabled: `reportError` only dynamic-imports the SDK after
 * `SentryInit` has initialized it.
 */
let sentryReady = false;

export function markSentryReady(): void {
  sentryReady = true;
}

export function reportError(error: unknown): void {
  if (!sentryReady) return;
  void import('@sentry/nextjs')
    .then((Sentry) => Sentry.captureException(error))
    .catch(() => undefined); // reporting must never crash the error UI
}
