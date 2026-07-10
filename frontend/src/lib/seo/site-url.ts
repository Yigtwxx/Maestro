import 'server-only';

import { PLACEHOLDER_SITE_URL } from './config';

/**
 * The public origin, scheme included, used for canonical URLs, `sitemap.xml`
 * and Open Graph tags.
 *
 * `SITE_URL` is deliberately not prefixed with `NEXT_PUBLIC_`: that prefix
 * makes webpack inline the value at build time, which would bake a domain into
 * the frontend image and break the one-image-many-hosts deployment (see
 * `docs/DEPLOYMENT.md`). Read server-side, at request time, it stays a runtime
 * lookup — hence the `server-only` guard above, and hence every caller must
 * first opt out of static rendering (`connection()` or `force-dynamic`).
 * Without that opt-out the value is read during `next build` and frozen.
 */
export function siteUrl(): string {
  // An unset variable arrives as `undefined`, but an empty or whitespace-only
  // one (e.g. `SITE_URL=` in a compose file) arrives as a string that `??`
  // would happily return — and `new URL('/', '')` throws. Treat both as unset.
  return process.env.SITE_URL?.trim() || PLACEHOLDER_SITE_URL;
}
