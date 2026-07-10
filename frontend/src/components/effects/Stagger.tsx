'use client';

import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import { staggerItem, useReducedMotion } from '@/lib/motion';

interface StaggerProps {
  children: ReactNode;
  className?: string;
  /** Per-child delay in seconds. */
  step?: number;
  /** Delay before the whole sequence starts (seconds). */
  delay?: number;
  /** Animate on mount instead of on scroll into view. */
  onMount?: boolean;
}

/**
 * Orchestrates staggered child entrances — wrap items in `StaggerItem`.
 * Renders plain divs under reduced motion.
 */
export function Stagger({
  children,
  className,
  step = 0.06,
  delay = 0,
  onMount = false,
}: StaggerProps) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      className={className}
      initial="hidden"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: step, delayChildren: delay } },
      }}
      {...(onMount
        ? { animate: 'visible' }
        : { whileInView: 'visible', viewport: { once: true, margin: '-40px' } })}
    >
      {children}
    </motion.div>
  );
}

/** Child of `Stagger` — scale pop + fade (inherits orchestration from parent). */
export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div className={className} variants={staggerItem}>
      {children}
    </motion.div>
  );
}
