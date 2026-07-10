// Motion design tokens — the single source of truth for durations, easings,
// springs and shared variants. Components must not hardcode ad-hoc timing;
// import from here so the whole app moves with one rhythm.

import type { Transition, Variants } from 'motion/react';

export { useReducedMotion } from 'motion/react';

/** Durations in seconds. */
export const DUR = {
  /** Hovers, presses. */
  fast: 0.15,
  /** Reveals, route transitions. */
  base: 0.25,
  /** Card/section entrances. */
  slow: 0.45,
  /** Showcase set-pieces. */
  cinematic: 0.8,
} as const;

/** Cubic-bezier easings. */
export const EASE = {
  /** Expo-out — all entrances. */
  out: [0.16, 1, 0.3, 1],
  /** Symmetric — crossfades. */
  inOut: [0.65, 0, 0.35, 1],
} as const;

/** Spring presets. */
export const SPRING = {
  /** Node/list pop-ins. */
  pop: { type: 'spring', stiffness: 260, damping: 24 } as const satisfies Transition,
};

/** Stagger timing — cap the total sequence at ~0.6s regardless of item count. */
export const STAGGER = {
  step: 0.06,
  maxTotal: 0.6,
} as const;

/** Per-item step that keeps `count` items within `STAGGER.maxTotal`. */
export function staggerStep(count: number): number {
  if (count <= 1) return 0;
  return Math.min(STAGGER.step, STAGGER.maxTotal / count);
}

/** Fade + rise + unblur entrance. */
export const revealVariants: Variants = {
  hidden: { opacity: 0, y: 12, filter: 'blur(6px)' },
  visible: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: DUR.slow, ease: EASE.out },
  },
};

/** Parent orchestrating staggered children (pair with `staggerItem`). */
export const staggerContainer: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: STAGGER.step } },
};

/** Child of `staggerContainer` — scale pop + fade. */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 8, scale: 0.96 },
  visible: { opacity: 1, y: 0, scale: 1, transition: SPRING.pop },
};
