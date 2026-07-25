import 'server-only';

/**
 * The Umami website id for this deployment, or `undefined` when analytics is
 * disabled — in which case no script is served, the storage notice stays
 * informational, and the consent question is never asked.
 *
 * `UMAMI_WEBSITE_ID` is deliberately not `NEXT_PUBLIC_`-prefixed: that prefix
 * makes webpack inline the value at build time, which would bake a
 * deployment-specific id into the frontend image and break the
 * one-image-many-hosts deployment (see `docs/DEPLOYMENT.md`). Read server-side,
 * at request time, it stays a runtime lookup — hence the `server-only` guard
 * above. The root layout, the only caller, is already dynamic via
 * `connection()`, so the value is never frozen by `next build`.
 */
export function umamiWebsiteId(): string | undefined {
  // Like SITE_URL: an empty or whitespace-only value in a compose file must
  // mean "unset", so `||` rather than `??`.
  return process.env.UMAMI_WEBSITE_ID?.trim() || undefined;
}
