'use client';

import type { CSSProperties, ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { useReducedMotion } from '@/lib/motion';
import { MODULE_COLOR, moduleFromPathname } from '@/lib/module-colors';

/**
 * Route transition — content renders instantly on every navigation (no enter
 * fade), so switching sidebar tabs feels immediate. A 1px module-tinted
 * scanline still sweeps down once as the page enters (the "signature" touch).
 */
export default function AppTemplate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const reduced = useReducedMotion();
  if (reduced) return <>{children}</>;

  const rgb = MODULE_COLOR[moduleFromPathname(pathname)].rgb;
  return (
    <>
      <span
        aria-hidden
        style={{ ['--pt-rgb' as string]: rgb } as CSSProperties}
        className="page-scanline"
      />
      {children}
    </>
  );
}
