'use client';

import type { CSSProperties, ReactNode } from 'react';
import { motion } from 'motion/react';
import { DUR, EASE, useReducedMotion } from '@/lib/motion';
import { MODULE_COLOR } from '@/lib/module-colors';

/** Auth route transition — lime-tinted variant of the app template. */
export default function AuthTemplate({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  if (reduced) return <>{children}</>;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DUR.base, ease: EASE.out }}
    >
      <span
        aria-hidden
        style={{ ['--pt-rgb' as string]: MODULE_COLOR.brand.rgb } as CSSProperties}
        className="page-scanline"
      />
      {children}
    </motion.div>
  );
}
