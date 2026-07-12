/**
 * Route slugs of the legal documents, separated from the registry so client
 * bundles can know the routes without importing the prose. `LEGAL_DOCS` types
 * its entries with {@link LegalSlug}, so this list and the registry cannot
 * drift apart without a compile error.
 */
export const LEGAL_SLUGS = [
  'terms',
  'privacy',
  'security',
  'acceptable-use',
  'cookies',
] as const;

export type LegalSlug = (typeof LEGAL_SLUGS)[number];
