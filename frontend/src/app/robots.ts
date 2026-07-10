import type { MetadataRoute } from 'next';

import { siteUrl } from '@/lib/seo/site-url';

/**
 * `SITE_URL` must be read per request, not baked into the build — see
 * `lib/seo/site-url.ts`.
 */
export const dynamic = 'force-dynamic';

/** Route prefixes behind authentication, plus the sign-in screens. */
const PRIVATE_PREFIXES = [
  '/dashboard',
  '/agents',
  '/architect',
  '/documents',
  '/marketplace',
  '/settings',
  '/login',
  '/register',
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: PRIVATE_PREFIXES,
    },
    sitemap: new URL('/sitemap.xml', siteUrl()).toString(),
  };
}
