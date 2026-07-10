import type { Metadata } from 'next';

import { OG_LOCALE, SITE_NAME } from './config';

interface PageMetadataInput {
  /** Without the brand suffix — the root layout's title template appends it. */
  title: string;
  description: string;
  /** Root-relative, e.g. `/pricing`. */
  path: string;
}

/**
 * Per-page metadata for a public page.
 *
 * The URLs stay relative on purpose: `metadataBase` in the root layout turns
 * them absolute at request time, so no page has to read `SITE_URL` itself and
 * no page has to opt out of static rendering on its own account.
 */
export function buildPageMetadata({
  title,
  description,
  path,
}: PageMetadataInput): Metadata {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: {
      type: 'website',
      siteName: SITE_NAME,
      locale: OG_LOCALE,
      title,
      description,
      url: path,
    },
    twitter: { card: 'summary_large_image', title, description },
  };
}
