// Cross-document serialization for refresh-token rotation.

import { REFRESH_LOCK_NAME } from '@/lib/constants';

/**
 * Run `fn` with the origin-wide refresh lock held.
 *
 * The access token lives only in a document's memory, so every page load has to
 * rotate the refresh cookie to get one. Several tabs restoring at once would
 * therefore replay the *same* cookie, and the backend's reuse-detection
 * (`auth_service.rotate_refresh_token`) reads a replay as token theft and burns
 * the whole session family — signing the user out on a routine reload.
 *
 * Serializing the rotation fixes it rather than merely narrowing the window: a
 * waiting tab only wakes after the winner's response — and so its `Set-Cookie`
 * — has landed in the shared jar, so it presents the successor token. That is a
 * chained rotation, which is exactly what the backend expects, not a replay.
 *
 * `locks` is a parameter so the behaviour can be tested without a DOM. It is
 * absent outside a secure context (a plain-HTTP LAN deployment), where the
 * fallback leaves only the in-document guard in `api.ts` — see
 * docs/CONFIGURATION.md.
 */
export async function withRefreshLock<T>(
  fn: () => Promise<T>,
  locks: LockManager | undefined = globalThis.navigator?.locks,
): Promise<T> {
  if (!locks) return fn();
  return locks.request(REFRESH_LOCK_NAME, fn);
}
