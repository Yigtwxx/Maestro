import { ACCOUNT_DELETION_GRACE_DAYS } from '@/lib/constants';

const MS_PER_DAY = 86_400_000;

/**
 * The date an account becomes irreversibly purged, derived from when deletion
 * was requested. The backend derives it the same way from the same constant --
 * it is never stored, so the two cannot drift.
 */
export function purgeDate(requestedAt: string): Date {
  return new Date(
    new Date(requestedAt).getTime() + ACCOUNT_DELETION_GRACE_DAYS * MS_PER_DAY,
  );
}

/** `10 August 2026`. Fixed locale so server and client markup agree. */
export function formatPurgeDate(requestedAt: string): string {
  return purgeDate(requestedAt).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}
