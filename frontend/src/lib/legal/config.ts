/**
 * Single source of truth for every operator-specific value in the legal
 * documents. The prose interpolates these, so incorporating a company means
 * editing this file and nothing else.
 */

export const LEGAL_ENTITY = {
  brand: 'Maestro',
  /** TODO: replace with the registered legal entity name once incorporated. */
  operatorName: 'Maestro',
  /** e.g. 'Ltd. Şti.', 'Inc.' — left blank while operated by an individual. */
  operatorType: '',
  /** TODO: registered address. */
  addressLine1: '',
  country: 'Türkiye',
  contactEmail: 'yigiterdogan023@gmail.com',
  /** Data-subject requests (KVKK Art.11 / GDPR Art.15-22) land here. */
  privacyEmail: 'yigiterdogan023@gmail.com',
  securityEmail: 'yigiterdogan023@gmail.com',
  governingLaw: 'the Republic of Türkiye',
  /** TODO: competent courts, e.g. 'the Istanbul Courts and Enforcement Offices'. */
  jurisdiction: 'the competent courts of the Republic of Türkiye',
  sourceUrl: 'https://github.com/Yigtwxx/maestro',
} as const;

/**
 * Whether a real, PCI-scoped payment processor is live.
 *
 * While this is `false` the platform runs on a mock provider: no card is
 * charged and no real payment is processed. The legal pages surface a
 * pre-release notice so the billing terms below can never be read as a claim
 * that money is actually changing hands. Flip to `true` — and only then —
 * once a real processor is integrated.
 */
export const BILLING_LIVE = false;

/** Shown wherever billing terms appear while `BILLING_LIVE` is false. */
export const BILLING_PRERELEASE_NOTICE =
  'Billing is in pre-release. No real payments are processed and no cards are charged. ' +
  'Do not enter real card details.';

/**
 * The Turkish-language KVKK notice is not written yet. Turkish law expects the
 * aydınlatma metni in a language the data subject understands, so this gap is
 * surfaced rather than hidden. Remove the notice once `tr/` content ships.
 */
export const KVKK_TURKISH_PENDING = true;

export const KVKK_TURKISH_NOTICE =
  'A Turkish-language KVKK aydınlatma metni is being prepared. Until it is published, ' +
  `this English text governs. Turkish-speaking users may request clarification at ${LEGAL_ENTITY.privacyEmail}.`;
