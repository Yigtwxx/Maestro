import type { Metadata } from 'next';
import { connection } from 'next/server';
import localFont from 'next/font/local';
import { Analytics } from '@/components/analytics/Analytics';
import { CookieNotice } from '@/components/legal/CookieNotice';
import { SentryInit } from '@/components/observability/SentryInit';
import { Toaster } from '@/components/ui/Toaster';
import { umamiWebsiteId } from '@/lib/analytics/config';
import { sentryClientConfig } from '@/lib/observability/config';
import { GITHUB_URL } from '@/lib/constants';
import {
  OG_LOCALE,
  SITE_DEFAULT_TITLE,
  SITE_DESCRIPTION,
  SITE_KEYWORDS,
  SITE_NAME,
  SITE_TAGLINE,
  TITLE_TEMPLATE,
} from '@/lib/seo/config';
import { siteUrl } from '@/lib/seo/site-url';
import './globals.css';

// Self-hosted so the build never depends on Google Fonts being reachable. The
// full variable woff2 files (wght axis, latin + latin-ext) live in ./fonts.
const jetbrainsMono = localFont({
  src: './fonts/JetBrainsMono-Variable.woff2',
  weight: '100 800',
  display: 'swap',
  variable: '--font-mono',
  fallback: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
});

const spaceGrotesk = localFont({
  src: './fonts/SpaceGrotesk-Variable.woff2',
  weight: '300 700',
  display: 'swap',
  variable: '--font-sans',
  fallback: ['ui-sans-serif', 'system-ui', 'sans-serif'],
});

/**
 * `metadataBase` makes every page's relative canonical and OG url absolute, so
 * it is the one place the public origin enters page metadata.
 *
 * `connection()` is what makes that origin correct. Without it this function
 * runs during `next build` and freezes whatever `SITE_URL` was set then — which
 * for a domain-agnostic image is nothing. It pushes rendering to request time,
 * so the value is read from the container's environment instead. The cost is
 * that no page under this layout prerenders statically; the marketing pages are
 * light server-rendered copy, and a canonical URL that is right everywhere is
 * worth more than their prerender.
 *
 * Neither `icons` nor `manifest` belongs here: `app/icon.svg` and
 * `app/manifest.ts` already emit their own `<link>` tags, and a value set here
 * would override them.
 */
export async function generateMetadata(): Promise<Metadata> {
  await connection();
  const base = siteUrl();

  return {
    metadataBase: new URL(base),
    title: { default: SITE_DEFAULT_TITLE, template: TITLE_TEMPLATE },
    description: SITE_DESCRIPTION,
    applicationName: SITE_NAME,
    authors: [{ name: SITE_NAME, url: GITHUB_URL }],
    keywords: [...SITE_KEYWORDS],
    robots: { index: true, follow: true },
    alternates: { canonical: '/' },
    openGraph: {
      type: 'website',
      siteName: SITE_NAME,
      locale: OG_LOCALE,
      title: SITE_DEFAULT_TITLE,
      description: SITE_TAGLINE,
      url: '/',
    },
    twitter: {
      card: 'summary_large_image',
      title: SITE_DEFAULT_TITLE,
      description: SITE_TAGLINE,
    },
  };
}

/**
 * Structured data for the site as a whole.
 *
 * Plans and prices are deliberately absent: the backend is their source of
 * truth, and an `offers` block here would drift the moment one changes.
 */
function buildJsonLd(base: string) {
  const organizationId = new URL('/#organization', base).toString();

  return {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': organizationId,
        name: SITE_NAME,
        url: base,
        sameAs: [GITHUB_URL],
      },
      {
        '@type': 'SoftwareApplication',
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        applicationCategory: 'DeveloperApplication',
        operatingSystem: 'Web',
        url: base,
        publisher: { '@id': organizationId },
      },
    ],
  };
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await connection();
  // Escaped so a future value containing `</script>` cannot close the tag.
  const jsonLd = JSON.stringify(buildJsonLd(siteUrl())).replace(/</g, '\\u003c');
  // Unset on deployments without analytics: no tracker mounts and the notice
  // stays informational. Read at request time, like SITE_URL above.
  const websiteId = umamiWebsiteId();
  // Same contract for error tracking: DSN unset means no SDK chunk is loaded.
  const sentry = sentryClientConfig();

  return (
    <html
      lang="en"
      className={`scroll-smooth scroll-pt-24 ${jetbrainsMono.variable} ${spaceGrotesk.variable}`}
    >
      {/* The route groups share no layout, so the notice mounts once, here. */}
      <body>
        {children}
        <CookieNotice analyticsAvailable={websiteId !== undefined} />
        {websiteId !== undefined && <Analytics websiteId={websiteId} />}
        {sentry !== undefined && (
          <SentryInit dsn={sentry.dsn} environment={sentry.environment} />
        )}
        <Toaster />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLd }}
        />
      </body>
    </html>
  );
}
