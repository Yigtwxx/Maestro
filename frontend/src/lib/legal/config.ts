/**
 * Single source of truth for every operator-specific value in the legal
 * documents. The prose interpolates these, so incorporating a company means
 * editing this file and nothing else.
 */

export const LEGAL_ENTITY = {
  brand: 'Maestro',
  /** Individual operator; replace with the registered legal entity name once incorporated. */
  operatorName: 'Yiğit Erdoğan',
  /** e.g. 'Ltd. Şti.', 'Inc.' — left blank while operated by an individual. */
  operatorType: '',
  /** No registered address — the service is operated by an individual; only the country is disclosed. */
  addressLine1: '',
  country: 'Türkiye',
  contactEmail: 'yigiterdogan023@gmail.com',
  /** Data-subject requests (KVKK Art.11 / GDPR Art.15-22) land here. */
  privacyEmail: 'yigiterdogan023@gmail.com',
  securityEmail: 'yigiterdogan023@gmail.com',
  governingLaw: 'the Republic of Türkiye',
  /**
   * No specific court is designated while the service is operated by an
   * individual; name one (e.g. 'the Istanbul Courts and Enforcement Offices')
   * once incorporated.
   */
  jurisdiction: 'the competent courts of the Republic of Türkiye',
  sourceUrl: 'https://github.com/Yigtwxx/Maestro',
} as const;

/**
 * Whether a real, PCI-scoped payment processor is live.
 *
 * While this is `false` the paid plans are parked: their CTAs read "coming
 * soon" and the billing surfaces are not reachable, except for admins, who keep
 * the live flow so the operator can test it. Every account runs on the free
 * plan instead. The legal pages surface a notice so the billing terms below can
 * never be read as a claim that money is changing hands. Flip to `true` — and
 * only then — once a real processor is integrated. Its backend twin is the
 * `BILLING_ENABLED` setting, which this process cannot read; flip both.
 */
export const BILLING_LIVE = false;

/**
 * Whether the email-verification soft gate is enforced.
 *
 * While this is `false` an unverified account can do everything a verified one
 * can, so the app must not nag anybody to verify: the reminder banner hides
 * itself and registration stops claiming a link was sent. The `/verify-email`
 * screen and the link/code endpoints keep working — nothing is disabled, it
 * simply is not demanded.
 *
 * It ships off because the default sender is `console`, which writes the
 * message to the server log instead of an inbox: a gate nobody can pass locks
 * the product rather than protecting it. Its backend twin is the
 * `EMAIL_VERIFICATION_REQUIRED` setting, which this process cannot read; flip
 * both, and only alongside a real sender.
 */
export const EMAIL_VERIFICATION_LIVE = false;

/** Shown wherever billing terms appear while `BILLING_LIVE` is false. */
export const BILLING_PRERELEASE_NOTICE =
  'Paid plans are coming soon. Every account currently runs on the free plan ' +
  'with unlimited tokens — no card is collected and no payment is processed.';
