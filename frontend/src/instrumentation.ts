import type { Instrumentation } from 'next';

/**
 * Reads the server-side Sentry DSN, treating unset and empty as the same thing.
 *
 * @returns The trimmed DSN, or `undefined` when Sentry is disabled.
 */
function resolveDsn(): string | undefined {
  return process.env.SENTRY_DSN?.trim() || undefined;
}

/**
 * Server-side Sentry. Runs once at server startup, in Node — so
 * `process.env.SENTRY_DSN` is a genuine runtime read and the image stays
 * domain-agnostic (no build-time inlining, unlike `NEXT_PUBLIC_*`).
 *
 * DSN unset or empty (self-hosters without a Sentry account): full no-op,
 * zero egress. Mirrors the backend's `init_sentry()` contract.
 *
 * `@sentry/nextjs` is imported dynamically rather than at module scope: a static
 * import makes the entire Sentry + OpenTelemetry graph (~8,500 files) a compile
 * edge of this instrumentation entry even when no DSN is configured, which is
 * dead weight on every dev compile and every build.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return;
  const dsn = resolveDsn();
  if (!dsn) return;

  const Sentry = await import('@sentry/nextjs');
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT?.trim() || 'production',
    tracesSampleRate: 0, // errors only — no APM, protects free-tier quota
    sendDefaultPii: false,
  });
  // No edge branch: this app has no middleware.ts and no edge routes.
}

/**
 * Captures Server Component / route handler render errors. A no-op when
 * `register()` skipped init above, so the dynamic import never runs either.
 */
export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (!resolveDsn()) return;
  const Sentry = await import('@sentry/nextjs');
  return Sentry.captureRequestError(...args);
};
