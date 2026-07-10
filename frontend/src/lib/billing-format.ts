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

export function formatQuota(tokens: number): string {
  if (tokens >= MILLION) return `${tokens / MILLION}M tokens / mo`;
  return `${tokens / THOUSAND}K tokens / mo`;
}
