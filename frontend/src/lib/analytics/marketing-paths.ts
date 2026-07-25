import { MARKETING_NAV_LINKS } from '@/lib/constants';
import { LEGAL_SLUGS } from '@/lib/legal/slugs';

/**
 * The exact pathnames analytics is ever allowed to see: the public marketing
 * pages. This is an inclusion list on purpose — a page that is not listed here
 * is never tracked, so a new app or auth route can never leak into analytics;
 * a new marketing page is merely uncounted until it is added.
 *
 * Derived from the same sources as the nav, footer, and sitemap
 * (`MARKETING_NAV_LINKS` + the legal registry slugs), so the only hand-kept
 * entries are the landing page and the `/legal` hub. All marketing routes are
 * flat today, which is why exact matching suffices.
 */
export const MARKETING_PATHS: ReadonlySet<string> = new Set([
  '/',
  '/legal',
  ...MARKETING_NAV_LINKS.map((link) => link.href),
  ...LEGAL_SLUGS.map((slug) => `/${slug}`),
]);

/** Whether a pathname is a public marketing page that may be counted. */
export function isMarketingPath(pathname: string): boolean {
  return MARKETING_PATHS.has(pathname);
}
