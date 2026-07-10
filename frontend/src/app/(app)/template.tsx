'use client';

import type { CSSProperties, ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { motion } from 'motion/react';
import { DUR, EASE, useReducedMotion } from '@/lib/motion';
import { MODULE_COLOR, moduleFromPathname } from '@/lib/module-colors';

/**
 * Route transition — App Router remounts templates per navigation, so an
 * enter-only fade + rise needs no exit orchestration. A 1px module-tinted
 * scanline sweeps down once as the page enters (the "signature" touch).
 */
export default function AppTemplate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const reduced = useReducedMotion();
  if (reduced) return <>{children}</>;

  const rgb = MODULE_COLOR[moduleFromPathname(pathname)].rgb;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.base, ease: EASE.out }}
    >
      <span
        aria-hidden
        style={{ ['--pt-rgb' as string]: rgb } as CSSProperties}
        className="page-scanline"
      />
      {children}
    </motion.div>
  );
}
