'use client';

import { useEffect, useState } from 'react';
import Script from 'next/script';
import { usePathname } from 'next/navigation';
import { isMarketingPath } from '@/lib/analytics/marketing-paths';
import { useConsentStore } from '@/stores/consent';

declare global {
  interface Window {
    /** Injected by the Umami tracker script once loaded. */
    umami?: { track: () => void };
  }
}

/**
 * Self-hosted Umami pageview tracking, mounted in the root layout only when
 * the deployment configured a website id.
 *
 * Consent-first: nothing renders — no script tag, no request — until the
 * consent store hydrates with `analytics === true`. Because that is only ever
 * true client-side, `window` exists by the time the script tag renders.
 *
 * Auto-tracking is off (`data-auto-track="false"`) on purpose. Umami's auto
 * mode hooks `history.pushState`, and a script listener survives its tag being
 * removed — a client-side navigation from a marketing page into the app would
 * keep firing events. Manual mode makes that leak structurally impossible:
 * every pageview is an explicit `umami.track()` call, gated on the pathname
 * being a public marketing page. It also makes consent withdrawal effective
 * immediately, without a reload — the loaded script is inert on its own.
 *
 * The script and the collect endpoint are same-origin under `/a` (Caddy
 * proxies them to the umami container; its native `/api/send` would collide
 * with the backend's `/api/*` route), so no analytics host is baked into the
 * image.
 */
export function Analytics({ websiteId }: { websiteId: string }) {
  const hydrated = useConsentStore((state) => state.hydrated);
  const analytics = useConsentStore((state) => state.analytics);
  const hydrate = useConsentStore((state) => state.hydrate);
  const pathname = usePathname();
  const [loaded, setLoaded] = useState(false);

  // Idempotent; CookieNotice also hydrates, but this component must not depend
  // on the notice being mounted or answered.
  useEffect(() => {
    hydrate();
  }, [hydrate]);

  // One pageview per pathname change (and one when the script first loads),
  // only while consented and only on marketing pages.
  useEffect(() => {
    if (loaded && analytics && isMarketingPath(pathname)) {
      window.umami?.track();
    }
  }, [loaded, analytics, pathname]);

  if (!hydrated || !analytics) return null;

  return (
    <Script
      src="/a/script.js"
      strategy="afterInteractive"
      data-website-id={websiteId}
      data-host-url={`${window.location.origin}/a`}
      data-auto-track="false"
      onLoad={() => setLoaded(true)}
    />
  );
}
