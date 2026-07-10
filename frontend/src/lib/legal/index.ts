/**
 * The legal document registry: one source of truth for the `/legal` hub, the
 * marketing footer, and each document's own page. Adding a document here is
 * enough to make it appear everywhere it should.
 */

import { ACCEPTABLE_USE } from './acceptable-use';
import { COOKIES } from './cookies';
import { PRIVACY } from './privacy';
import { SECURITY } from './security';
import { TERMS } from './terms';

/** Prepared for a Turkish translation; every document is English for now. */
export type LegalLocale = 'en';

export interface LegalDoc {
  /** Route segment: the document lives at `/{slug}`. */
  slug: string;
  title: string;
  /** One line, shown on the hub cards and as the page description. */
  description: string;
  /** ISO date of the last substantive revision. */
  updated: string;
  locale: LegalLocale;
  content: string;
}

export const LEGAL_DOCS: readonly LegalDoc[] = [
  {
    slug: 'terms',
    title: 'Terms of Service',
    description:
      'The agreement between you and Maestro: accounts, BYOK, subscriptions, refunds, and liability.',
    updated: '2026-07-10',
    locale: 'en',
    content: TERMS,
  },
  {
    slug: 'privacy',
    title: 'Privacy Policy',
    description:
      'What we collect, why, who we share it with, how long we keep it, and your rights under GDPR and KVKK.',
    updated: '2026-07-10',
    locale: 'en',
    content: PRIVACY,
  },
  {
    slug: 'security',
    title: 'Security',
    description:
      'How your API keys are encrypted, how tenants are isolated, how agents are contained — and what we do not claim.',
    updated: '2026-07-10',
    locale: 'en',
    content: SECURITY,
  },
  {
    slug: 'acceptable-use',
    title: 'Acceptable Use Policy',
    description:
      'What you may and may not point an autonomous agent at. Part of the Terms of Service.',
    updated: '2026-07-10',
    locale: 'en',
    content: ACCEPTABLE_USE,
  },
  {
    slug: 'cookies',
    title: 'Cookie Policy',
    description:
      'We set no cookies and run no tracking. Here is the short list of what we do store, and why.',
    updated: '2026-07-10',
    locale: 'en',
    content: COOKIES,
  },
] as const;

/** Footer links. Sourced from the registry so the two can never drift apart. */
export const LEGAL_FOOTER_LINKS = LEGAL_DOCS.map((doc) => ({
  href: `/${doc.slug}`,
  label: doc.title,
}));

export function legalDoc(slug: string): LegalDoc {
  const doc = LEGAL_DOCS.find((candidate) => candidate.slug === slug);
  if (doc === undefined) {
    throw new Error(`Unknown legal document: ${slug}`);
  }
  return doc;
}

/** `2026-07-10` -> `10 July 2026`. Fixed locale so SSR and client agree. */
export function formatLegalDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export { BILLING_LIVE, BILLING_PRERELEASE_NOTICE, KVKK_TURKISH_NOTICE, KVKK_TURKISH_PENDING, LEGAL_ENTITY } from './config';
