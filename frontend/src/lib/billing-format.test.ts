import { describe, expect, it } from 'vitest';
import { formatPrice, formatQuota, isUnlimitedQuota } from './billing-format';

describe('isUnlimitedQuota', () => {
  it('recognises the backend sentinel', () => {
    expect(isUnlimitedQuota(-1)).toBe(true);
  });

  it('treats any real allowance as capped', () => {
    expect(isUnlimitedQuota(500_000)).toBe(false);
    expect(isUnlimitedQuota(0)).toBe(false);
  });
});

describe('formatQuota', () => {
  it('names the unlimited plan instead of doing arithmetic on the sentinel', () => {
    // Without the guard this rendered '-0.001K tokens / mo' on both grids.
    expect(formatQuota(-1)).toBe('Unlimited tokens');
  });

  it('renders millions and thousands', () => {
    expect(formatQuota(3_000_000)).toBe('3M tokens / mo');
    expect(formatQuota(500_000)).toBe('500K tokens / mo');
  });
});

describe('formatPrice', () => {
  it('renders a free plan as zero, not blank', () => {
    expect(formatPrice(0, 'usd')).toBe('$0');
  });

  it('renders whole-dollar amounts without cents', () => {
    expect(formatPrice(1_500, 'usd')).toBe('$15');
  });
});
