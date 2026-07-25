// Central date/time formatting. Every human-facing timestamp goes through here
// so a user's timezone preference (users.timezone) can be applied in ONE place.
// When no timezone is passed the browser's local zone is used (Intl default).
//
// The LOCALE is pinned to English (the app's only UI language until i18n lands)
// rather than left to the browser default. Passing `undefined` used the visitor's
// system locale, so a Turkish browser rendered "13 Tem 2026" / "21 dakika önce"
// inside an otherwise-English UI. en-GB keeps the intended day-first "12 Jul 2026".
// This matches the explicit 'en'/'en-US'/'en-GB' locales used elsewhere
// (HistoryPanel, QuotaMeter, billing-format, legal, deletion).

import { useAuthStore } from '@/stores/auth';

const LOCALE = 'en-GB';

function fmt(
  iso: string | number | Date,
  options: Intl.DateTimeFormatOptions,
  timeZone: string | null | undefined,
): string {
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(LOCALE, {
    ...options,
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}

/** e.g. "12 Jul 2026". */
export function formatDate(
  iso: string | number | Date,
  timeZone?: string | null,
): string {
  return fmt(iso, { day: '2-digit', month: 'short', year: 'numeric' }, timeZone);
}

/** e.g. "12 Jul 2026, 14:30". */
export function formatDateTime(
  iso: string | number | Date,
  timeZone?: string | null,
): string {
  return fmt(
    iso,
    {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    },
    timeZone,
  );
}

/** e.g. "14:30:07". */
export function formatTime(
  iso: string | number | Date,
  timeZone?: string | null,
): string {
  return fmt(
    iso,
    { hour: '2-digit', minute: '2-digit', second: '2-digit' },
    timeZone,
  );
}

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
];

/** Timezone-agnostic "3 hours ago" / "just now". */
export function relativeTime(iso: string | number | Date): string {
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return 'just now';
  const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' });
  for (const [unit, unitSeconds] of RELATIVE_UNITS) {
    if (abs >= unitSeconds) {
      return rtf.format(Math.round(seconds / unitSeconds), unit);
    }
  }
  return rtf.format(seconds, 'second');
}

/**
 * The current user's preferred IANA timezone, or undefined to fall back to the
 * browser's local zone. Use inside components, then pass to the formatters.
 */
export function useTimeZone(): string | undefined {
  return useAuthStore((s) => s.user?.timezone ?? undefined);
}
