import { ImageResponse } from 'next/og';

import { BRAND, SITE_DEFAULT_TITLE, SITE_NAME, SITE_TAGLINE } from '@/lib/seo/config';
import { Monogram } from '@/lib/seo/og-monogram';

export const alt = SITE_DEFAULT_TITLE;
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

/**
 * The social card, drawn once at build time.
 *
 * It reads no environment variable, which is what keeps it static: pull
 * `siteUrl()` in here and the route turns dynamic, regenerating the same PNG on
 * every crawl. The Node runtime is required — satori rasterises through WASM,
 * which the edge runtime cannot load from the standalone output.
 */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 44,
          width: '100%',
          height: '100%',
          padding: '0 96px',
          background: BRAND.background,
          color: BRAND.white,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 34 }}>
          <Monogram size={132} radius={28} />
          <div
            style={{
              display: 'flex',
              fontSize: 104,
              fontWeight: 700,
              letterSpacing: '0.04em',
            }}
          >
            {SITE_NAME.toUpperCase()}
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            maxWidth: 900,
            fontSize: 42,
            lineHeight: 1.35,
            color: BRAND.lime,
          }}
        >
          {SITE_TAGLINE}
        </div>
      </div>
    ),
    { ...size },
  );
}
