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
  lime: '#a3e635',
  background: '#0a0a10',
  black: '#000000',
  white: '#ffffff',
} as const;

/**
 * The Maestro monogram: an "M" traced as two peaks and a valley. Identical to
 * the inline SVG in `components/landing/LandingNav.tsx`; drawn on a 24×24
 * viewBox with a stroke width of 2.4.
 */
export const MONOGRAM_PATH = 'M5 17V7l7 6 7-6v10';
export const MONOGRAM_VIEWBOX = '0 0 24 24';
export const MONOGRAM_STROKE_WIDTH = 2.4;
