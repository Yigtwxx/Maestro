import type { MetadataRoute } from 'next';

import { BRAND, SITE_DESCRIPTION, SITE_NAME } from '@/lib/seo/config';

/**
 * Served at `/manifest.webmanifest`. Next links it from every page on its own,
 * so the root layout must not also declare `metadata.manifest`.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE_NAME,
    short_name: SITE_NAME,
    description: SITE_DESCRIPTION,
    start_url: '/',
    display: 'standalone',
    background_color: BRAND.background,
    theme_color: BRAND.lime,
    icons: [
      { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml' },
      { src: '/apple-icon', sizes: '180x180', type: 'image/png' },
    ],
  };
}
