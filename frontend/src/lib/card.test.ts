import { describe, it, expect } from 'vitest';
import {
  cardAcceptable,
  cardExpired,
  detectBrand,
  formatCardNumber,
  luhnValid,
  sanitize,
} from '@/lib/card';

// Standard scheme test numbers (valid Luhn, never real cards).
const VISA = '4242424242424242';
const MASTERCARD_LEGACY = '5555555555554444';
const MASTERCARD_2SERIES = '2223003122003222';
const AMEX = '378282246310005'; // a real scheme, but not one Maestro accepts

describe('sanitize', () => {
  it('strips spaces and dashes', () => {
    expect(sanitize('4242 4242-4242 4242')).toBe(VISA);
  });
});

describe('luhnValid', () => {
  it('accepts a number with a correct checksum', () => {
    expect(luhnValid(VISA)).toBe(true);
    expect(luhnValid(MASTERCARD_LEGACY)).toBe(true);
  });

  it('rejects a number with a broken checksum', () => {
    expect(luhnValid('4242424242424241')).toBe(false);
  });

  it('rejects a too-short number', () => {
    expect(luhnValid('4242')).toBe(false);
  });

  it('rejects non-digit input', () => {
    expect(luhnValid('4242abcd42424242')).toBe(false);
  });
});

describe('detectBrand', () => {
  it('identifies Visa', () => {
    expect(detectBrand(VISA)).toBe('visa');
  });

  it('identifies both Mastercard ranges', () => {
    expect(detectBrand(MASTERCARD_LEGACY)).toBe('mastercard');
    expect(detectBrand(MASTERCARD_2SERIES)).toBe('mastercard');
  });

  it('returns undefined for an unaccepted scheme', () => {
    expect(detectBrand(AMEX)).toBeUndefined();
  });
});

describe('formatCardNumber', () => {
  it('groups digits in fours', () => {
    expect(formatCardNumber(VISA)).toBe('4242 4242 4242 4242');
  });

  it('ignores non-digits and caps at 19 digits', () => {
    expect(formatCardNumber('4242abcd4242')).toBe('4242 4242');
    // Capped at 19 digits, so the last group holds only three.
    expect(formatCardNumber('4'.repeat(25))).toBe('4444 4444 4444 4444 444');
  });
});

describe('cardExpired', () => {
  // Reference "now" = July 2026, so month math is deterministic.
  const now = new Date(2026, 6, 15);

  it('treats a past year or month as expired', () => {
    expect(cardExpired(12, 2025, now)).toBe(true);
    expect(cardExpired(6, 2026, now)).toBe(true);
  });

  it('is valid through the last day of the expiry month', () => {
    expect(cardExpired(7, 2026, now)).toBe(false);
    expect(cardExpired(8, 2026, now)).toBe(false);
    expect(cardExpired(1, 2030, now)).toBe(false);
  });
});

describe('cardAcceptable', () => {
  it('accepts a valid, unexpired, supported card', () => {
    expect(cardAcceptable('4242 4242 4242 4242', 12, 2030)).toBe(true);
  });

  it('rejects an expired card', () => {
    expect(cardAcceptable(VISA, 1, 2000)).toBe(false);
  });

  it('rejects an unsupported scheme even with a valid checksum', () => {
    expect(cardAcceptable(AMEX, 12, 2030)).toBe(false);
  });

  it('rejects a broken checksum', () => {
    expect(cardAcceptable('4242424242424241', 12, 2030)).toBe(false);
  });
});
