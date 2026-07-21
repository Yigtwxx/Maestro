'use client';

import { useSyncExternalStore } from 'react';
import LightRays from '@/components/effects/reactbits/LightRays';
import SideRays from '@/components/effects/reactbits/SideRays';
import { DOMAIN_COLOR } from '@/lib/agent-colors';
import { BRAND } from '@/lib/seo/config';

// Four distinct neon hues, one per light source. Three are pulled from the
// domain color source of truth; the center-right beam carries the brand.
const CYAN = DOMAIN_COLOR.searching.accentHex; //  #22d3ee — top-left corner
const MAGENTA = DOMAIN_COLOR.content.accentHex; // #e879f9 — center-left beam
const BRAND_BEAM = BRAND.primary; //               #d3cbc0 — center-right beam (champagne brand)
const ORANGE = DOMAIN_COLOR.data.accentHex; //     #ff7a45 — top-right corner

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

// Subscribe to the reduced-motion media query without a setState-in-effect. The
// server snapshot is `false` so SSR (and the first client paint) render the rays;
// a reduced-motion client then re-renders to the static fallback.
function subscribeReducedMotion(callback: () => void): () => void {
  const mq = window.matchMedia(REDUCED_MOTION_QUERY);
  mq.addEventListener('change', callback);
  return () => mq.removeEventListener('change', callback);
}

function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    () => false,
  );
}

/**
 * Landing light field built from React Bits WebGL backgrounds:
 * two LightRays falling toward the center (magenta + periwinkle brand) and two SideRays
 * sweeping in from the top corners (cyan left, pink right). Each ray sits in its
 * own `screen`-blended layer so overlaps brighten toward white like real light.
 *
 * The field is `pointer-events-none` and behind the page content (z-0). Its host
 * (see `page.tsx`) pins it to the viewport with `position: fixed`, so the canvas
 * stays viewport-sized — keeping the beam proportions crisp — while every section
 * scrolled under it is lit from the top, carrying the light to the page bottom.
 *
 * Under `prefers-reduced-motion` the WebGL canvases never mount; a static neon
 * gradient stands in instead, matching the site's reduced-motion policy.
 */
export default function RayLights() {
  const reducedMotion = usePrefersReducedMotion();

  // Static fallback when motion is reduced: a soft neon wash so the field is
  // never a flat black void.
  if (reducedMotion) {
    return (
      <div
        className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
        aria-hidden
        style={{
          background:
            `radial-gradient(45% 40% at 0% 0%, rgb(34 211 238 / 0.14), transparent 70%),` +
            `radial-gradient(60% 45% at 38% 0%, rgb(232 121 249 / 0.16), transparent 70%),` +
            `radial-gradient(60% 45% at 62% 0%, rgb(211 203 192 / 0.16), transparent 70%),` +
            `radial-gradient(45% 40% at 100% 0%, rgb(255 122 69 / 0.14), transparent 70%)`,
        }}
      />
    );
  }

  return (
    <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden>
      {/* Center LightRays — magenta. Full-width host so the top-center origin sits
          at the screen centre (not 1/3), and the beam never hits a container edge
          to clip into a vertical seam. A wide spread keeps it a soft ambient wash
          behind the hero rather than a defined shaft framing the text. */}
      <div className="absolute inset-0" style={{ mixBlendMode: 'screen' }}>
        <LightRays
          raysOrigin="top-center"
          raysColor={MAGENTA}
          followMouse={false}
          lightSpread={1.6}
          rayLength={2.8}
          raysSpeed={1}
          fadeDistance={1.9}
          saturation={1.3}
        />
      </div>

      {/* Center LightRays — periwinkle brand. Same centred, full-width host; the
          two beams overlap into one warm central glow via the screen blend. */}
      <div className="absolute inset-0" style={{ mixBlendMode: 'screen' }}>
        <LightRays
          raysOrigin="top-center"
          raysColor={BRAND_BEAM}
          followMouse={false}
          lightSpread={1.6}
          rayLength={2.8}
          raysSpeed={1.05}
          fadeDistance={1.9}
          saturation={1.3}
        />
      </div>

      {/* Top-left corner SideRays — cyan (single hue). */}
      <div className="absolute inset-0" style={{ mixBlendMode: 'screen' }}>
        <SideRays
          origin="top-left"
          rayColor1={CYAN}
          rayColor2={CYAN}
          intensity={3.2}
          spread={1.8}
          saturation={1.4}
          falloff={1.7}
          opacity={1}
          speed={2}
        />
      </div>

      {/* Top-right corner SideRays — orange (single hue). */}
      <div className="absolute inset-0" style={{ mixBlendMode: 'screen' }}>
        <SideRays
          origin="top-right"
          rayColor1={ORANGE}
          rayColor2={ORANGE}
          intensity={3.2}
          spread={1.8}
          saturation={1.4}
          falloff={1.7}
          opacity={1}
          speed={2}
        />
      </div>
    </div>
  );
}
