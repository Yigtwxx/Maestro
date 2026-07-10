import type { MetadataRoute } from 'next';

import { MARKETING_NAV_LINKS } from '@/lib/constants';
import { LEGAL_DOCS } from '@/lib/legal';
import { siteUrl } from '@/lib/seo/site-url';

/**
 * `SITE_URL` must be read per request, not baked into the build — see
 * `lib/seo/site-url.ts`. Unlike page metadata, a sitemap has no `metadataBase`
 * to make its URLs absolute, so it builds them itself.
 */
export const dynamic = 'force-dynamic';

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  const absolute = (path: string): string => new URL(path, base).toString();

  return [
    { url: absolute('/'), changeFrequency: 'weekly', priority: 1 },

    // Derived from the nav rather than listed again, so a new marketing tab
    // cannot ship without appearing in the sitemap.
    ...MARKETING_NAV_LINKS.map((link) => ({
      url: absolute(link.href),
      changeFrequency: 'weekly' as const,
      priority: 0.8,
    })),

    // The hub is not a nav tab, which makes it the one path written by hand.
    { url: absolute('/legal'), changeFrequency: 'yearly', priority: 0.3 },

    ...LEGAL_DOCS.map((doc) => ({
      url: absolute(`/${doc.slug}`),
      lastModified: new Date(doc.updated),
      changeFrequency: 'yearly' as const,
      priority: 0.3,
    })),
  ];
}
