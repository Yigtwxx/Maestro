// Client mirror of backend app/services/payment/card.py, for live form
// validation. The server revalidates everything; this only keeps the user from
// submitting a card that was never going to work.

import type { CardBrand } from '@/types';

const VISA = /^4\d{12,18}$/;
const MASTERCARD_LEGACY = /^5[1-5]\d{14}$/;
// The 2-series covers BINs 2221-2720 inclusive.
const MASTERCARD_2_SERIES = /^2(?:22[1-9]|2[3-9]\d|[3-6]\d\d|7[01]\d|720)\d{12}$/;

const MIN_CARD_LENGTH = 12;
const GROUP_SIZE = 4;

/** Strip the spaces and dashes users type into card fields. */
export function sanitize(value: string): string {
  return value.replace(/[\s-]/g, '');
}

/** Verify the Luhn (mod-10) checksum of a sanitized card number. */
export function luhnValid(number: string): boolean {
  if (!/^\d+$/.test(number) || number.length < MIN_CARD_LENGTH) return false;

  let total = 0;
  for (let i = 0; i < number.length; i += 1) {
    let digit = Number(number[number.length - 1 - i]);
    if (i % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  }
  return total % 10 === 0;
}

/** Return the card scheme, or undefined if it is not one we accept. */
export function detectBrand(number: string): CardBrand | undefined {
  if (VISA.test(number)) return 'visa';
  if (MASTERCARD_LEGACY.test(number) || MASTERCARD_2_SERIES.test(number)) {
    return 'mastercard';
  }
  return undefined;
}

/** Group digits in fours as the user types. */
export function formatCardNumber(value: string): string {
  const digits = sanitize(value).replace(/\D/g, '').slice(0, 19);
  const groups = digits.match(new RegExp(`.{1,${GROUP_SIZE}}`, 'g'));
  return groups ? groups.join(' ') : '';
}

/** A card is valid through the last day of its expiry month. */
export function cardExpired(expMonth: number, expYear: number, now = new Date()): boolean {
  const currentMonth = now.getMonth() + 1;
  const currentYear = now.getFullYear();
  return expYear < currentYear || (expYear === currentYear && expMonth < currentMonth);
}

/** Whether the form is safe to submit: accepted scheme, valid checksum, unexpired. */
export function cardAcceptable(
  rawNumber: string,
  expMonth: number,
  expYear: number,
): boolean {
  const number = sanitize(rawNumber);
  return (
    luhnValid(number) &&
    detectBrand(number) !== undefined &&
    !cardExpired(expMonth, expYear)
  );
}
