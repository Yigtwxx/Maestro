import { BILLING_LIVE } from '@/lib/legal';
import type { UserPublic } from '@/types';

/**
 * Whether the paid-billing surfaces should be reachable for this viewer.
 *
 * Paid plans are parked while no real payment processor is integrated, so
 * ordinary accounts see "coming soon" instead of a checkout they cannot
 * complete. Admins keep the live flow: the operator has to be able to exercise
 * subscribe/cancel before it opens to everyone.
 *
 * One definition on purpose — the sidebar, the profile card, the billing page
 * and the plan grid all read it, and a second copy would drift. The backend
 * enforces the same rule independently in `billing._require_billing_reachable`;
 * this only decides what is rendered.
 */
export function canReachBilling(user: UserPublic | undefined): boolean {
  return BILLING_LIVE || user?.role === 'admin';
}
