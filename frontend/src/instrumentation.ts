import * as Sentry from '@sentry/nextjs';

/**
 * Server-side Sentry. Runs once at server startup, in Node — so
 * `process.env.SENTRY_DSN` is a genuine runtime read and the image stays
 * domain-agnostic (no build-time inlining, unlike `NEXT_PUBLIC_*`).
 *
 * DSN unset or empty (self-hosters without a Sentry account): full no-op,
 * zero egress. Mirrors the backend's `init_sentry()` contract.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const dsn = process.env.SENTRY_DSN?.trim();
    if (!dsn) return;
    Sentry.init({
      dsn,
      environment: process.env.SENTRY_ENVIRONMENT?.trim() || 'production',
      tracesSampleRate: 0, // errors only — no APM, protects free-tier quota
      sendDefaultPii: false,
    });
  }
  // No edge branch: this app has no middleware.ts and no edge routes.
}

// Captures Server Component / route handler render errors; a no-op when
// `register()` skipped init above.
export const onRequestError = Sentry.captureRequestError;
