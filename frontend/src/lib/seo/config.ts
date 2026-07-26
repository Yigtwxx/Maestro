/**
 * Brand facts the SEO surface needs, in one place. Client-safe: this module
 * reads no environment variable, so it may be imported from anywhere. The
 * runtime origin lives in `site-url.ts`, which is server-only.
 */

import { LEGAL_ENTITY } from '@/lib/legal/config';

/** The brand name already has a source of truth; do not introduce a second. */
export const SITE_NAME = LEGAL_ENTITY.brand;

export const SITE_DEFAULT_TITLE = `${SITE_NAME} — AI Agent Orchestration`;

/** Every page title flows through this, so the suffix is written once. */
export const TITLE_TEMPLATE = `%s — ${SITE_NAME}`;

export const SITE_DESCRIPTION =
  'Automate tasks with a multi-layer AI agent hierarchy using your own API keys.';

/** Mirrors the landing hero, trimmed to fit an Open Graph card. */
export const SITE_TAGLINE =
  'Multi-layer AI agent orchestration — one prompt, automated end to end.';

export const OG_LOCALE = 'en_US';

export const SITE_KEYWORDS = [
  'AI agent orchestration',
  'multi-agent',
  'BYOK',
  'LLM automation',
  'agent marketplace',
] as const;

/**
 * Used when `SITE_URL` is unset. Canonical URLs must be absolute, and an
 * undefined `metadataBase` is a build error — so there is always a fallback.
 * It is deliberately a placeholder domain: a wrong absolute URL is obvious,
 * whereas a plausible one would quietly ship.
 */
export const PLACEHOLDER_SITE_URL = 'https://maestro.example.com';

/**
 * Generated images cannot read Tailwind classes, so the few brand colors they
 * need are duplicated here. These mirror `tailwind.config.ts`: `primary.DEFAULT`
 * and `background`.
 */
export const BRAND = {
  primary: '#d3cbc0',
  background: '#0a0a10',
  black: '#000000',
  white: '#ffffff',
  /**
   * The monogram stroke. A single navy for satori-rendered marks (the OG card
   * and Apple touch icon): satori's inline-SVG gradient support is unreliable,
   * so those fall back to the middle stop of `MONOGRAM_GRADIENT`.
   */
  navy: '#3b5bdb',
} as const;

/**
 * The Maestro monogram: a bespoke, single-stroke signature "M" — an entry hook
 * rising through two peaks and a rounded valley, closed by an upward flourish.
 * Drawn on a 24×24 viewBox so `app/icon.svg` can center it with a translate and
 * satori can size it directly. Mirrored, letter for letter, by the inline copy
 * in `app/icon.svg`; every other surface renders it through the constants here
 * (`components/brand/BrandMark.tsx` in the DOM, `og-monogram.tsx` in satori).
 */
export const MONOGRAM_PATH =
  'M2.8 15.4C3.1 17.7 3.8 19 4.7 19C6 19 6.1 8.6 7.7 6C8.1 5.3 8.7 5.6 9 6.4C9.9 9 10.8 12.4 12 12.4C13.2 12.4 14.1 9 15 6.4C15.3 5.6 15.9 5.3 16.3 6C17.9 8.6 18 19 19.3 19C20.6 19 21.6 15.8 22.9 11.2';
export const MONOGRAM_VIEWBOX = '0 0 24 24';
export const MONOGRAM_STROKE_WIDTH = 2.1;

/**
 * Navy gloss gradient for the monogram stroke, top-lit (bright → dark). Used in
 * the DOM by `BrandMark`; mirrored as static stops in `app/icon.svg` (a static
 * file cannot import). satori marks use `BRAND.navy` instead — see above.
 */
export const MONOGRAM_GRADIENT = ['#4d7cff', '#3b5bdb', '#141a3c'] as const;
