'use client';

import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { cn } from '@/lib/cn';
import { DUR, EASE, useReducedMotion } from '@/lib/motion';

interface RevealProps {
  children: ReactNode;
  className?: string;
  /** Delay before the entrance starts (seconds). */
  delay?: number;
  /** Vertical travel in px. */
  y?: number;
  /** Blur-in strength in px (0 disables the filter). */
  blur?: number;
  /** Animate on mount instead of on scroll into view. */
  onMount?: boolean;
}

/**
 * Fade + rise + unblur entrance wrapper. Defaults to `whileInView` (fires once
 * when scrolled into view); set `onMount` for above-the-fold choreography.
 * Renders a plain div under reduced motion.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  y = 12,
  blur = 6,
  onMount = false,
}: RevealProps) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  const initial = { opacity: 0, y, filter: `blur(${blur}px)` };
  const visible = {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: DUR.slow, ease: EASE.out, delay },
  };
  return (
    <motion.div
      className={cn(className)}
      initial={initial}
      {...(onMount
        ? { animate: visible }
        : { whileInView: visible, viewport: { once: true, margin: '-40px' } })}
    >
      {children}
    </motion.div>
  );
}
