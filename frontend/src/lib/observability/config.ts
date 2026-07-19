import 'server-only';

export interface SentryClientConfig {
  dsn: string;
  environment: string;
}

/**
 * The frontend Sentry DSN for this deployment, or `undefined` when error
 * tracking is disabled — in which case the Sentry chunk is never loaded and
 * the browser makes zero requests to any ingest host.
 *
 * `SENTRY_DSN` is deliberately not `NEXT_PUBLIC_`-prefixed: that prefix makes
 * the bundler inline the value at build time, which would bake a
 * deployment-specific DSN into the frontend image and break the
 * one-image-many-hosts deployment (see `docs/DEPLOYMENT.md`). Read
 * server-side, at request time, it stays a runtime lookup — hence the
 * `server-only` guard above. The root layout, the only caller, is already
 * dynamic via `connection()`, so the value is never frozen by `next build`.
 */
export function sentryClientConfig(): SentryClientConfig | undefined {
  // Like SITE_URL: an empty or whitespace-only value in a compose file must
  // mean "unset", so `||` rather than `??`.
  const dsn = process.env.SENTRY_DSN?.trim() || undefined;
  if (dsn === undefined) return undefined;
  return {
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT?.trim() || 'production',
  };
}
