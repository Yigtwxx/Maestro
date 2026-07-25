// IANA timezone options for the preferences picker. Prefer the browser's full
// list (Intl.supportedValuesOf) so the choice is honest and complete; fall back
// to a curated set on older engines that lack the API.

const FALLBACK_TIMEZONES = [
  'UTC',
  'Europe/Istanbul',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'Europe/Moscow',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Australia/Sydney',
];

/** All IANA timezones the runtime knows, or a curated fallback. */
export function listTimezones(): string[] {
  const intl = Intl as typeof Intl & {
    supportedValuesOf?: (key: string) => string[];
  };
  if (typeof intl.supportedValuesOf === 'function') {
    try {
      return intl.supportedValuesOf('timeZone');
    } catch {
      // Fall through to the curated list.
    }
  }
  return FALLBACK_TIMEZONES;
}

/** The browser's current IANA timezone (for the "auto" hint). */
export function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}
