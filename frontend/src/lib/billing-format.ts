// Shared plan formatting, used by the in-app billing grid and the public
// pricing page so the two can never render the same plan differently.

const CENTS_PER_UNIT = 100;
const MILLION = 1_000_000;
const THOUSAND = 1_000;

export function formatPrice(cents: number, currency: string): string {
  const amount = cents / CENTS_PER_UNIT;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency.toUpperCase(),
    minimumFractionDigits: 0,
  }).format(amount);
}

/**
 * Mirrors the backend UNLIMITED_TOKEN_QUOTA sentinel (core/constants.py).
 *
 * The free plan reports a negative allowance rather than a huge number, so
 * every consumer must branch on this before doing arithmetic with
 * `quota_tokens` — otherwise a meter renders a nonsense bar and `formatQuota`
 * prints `-0.001K tokens / mo`.
 */
export function isUnlimitedQuota(tokens: number): boolean {
  return tokens < 0;
}

export function formatQuota(tokens: number): string {
  if (isUnlimitedQuota(tokens)) return 'Unlimited tokens';
  if (tokens >= MILLION) return `${tokens / MILLION}M tokens / mo`;
  return `${tokens / THOUSAND}K tokens / mo`;
}
