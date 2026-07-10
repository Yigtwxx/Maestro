import { ImageResponse } from 'next/og';

import { SITE_NAME } from '@/lib/seo/config';
import { Monogram } from '@/lib/seo/og-monogram';

export const alt = SITE_NAME;
export const size = { width: 180, height: 180 };
export const contentType = 'image/png';

/** iOS home-screen icon. Generated as a PNG because Safari ignores an SVG one. */
export default function AppleIcon() {
  return new ImageResponse(<Monogram size={size.width} radius={40} />, { ...size });
}
