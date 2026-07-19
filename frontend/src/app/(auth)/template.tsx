'use client';

import type { CSSProperties, ReactNode } from 'react';
import { MODULE_COLOR } from '@/lib/module-colors';

/**
 * Auth route transition — lime-tinted variant of the app template. Content
 * renders instantly with no JS-gated fade, so the sign-in form is visible
 * straight from the server render even if hydration is slow or fails; a 1px
 * brand-tinted scanline still sweeps down once on entry. The parent layout's
 * `animate-word-in` supplies the CSS-only entrance, and the scanline is hidden
 * under `prefers-reduced-motion` via globals.css.
 */
export default function AuthTemplate({ children }: { children: ReactNode }) {
  return (
    <>
      <span
        aria-hidden
        style={{ ['--pt-rgb' as string]: MODULE_COLOR.brand.rgb } as CSSProperties}
        className="page-scanline"
      />
      {children}
    </>
  );
}
