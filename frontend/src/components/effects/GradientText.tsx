// Adapted from React Bits "Gradient Text" (GradientText-TS-TW,
// https://reactbits.dev/text-animations/gradient-text) — the original drives
// the pan with a persistent rAF loop via motion; this version is pure CSS
// (`gradient-pan` keyframe, alternate = the original's yoyo), server-safe.
// Under reduced motion the gradient stays as a static fill.

import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface GradientTextProps {
  children: ReactNode;
  className?: string;
  /** Gradient stops — defaults to the brand→cyan sweep. */
  colors?: string[];
  /** Full pan duration in seconds. */
  speed?: number;
}

/** Animated gradient sweeping across live text. */
export function GradientText({
  children,
  className,
  colors = ['#d3cbc0', '#22d3ee', '#d3cbc0'],
  speed = 4,
}: GradientTextProps) {
  const style: CSSProperties = {
    backgroundImage: `linear-gradient(to right, ${colors.join(', ')})`,
    backgroundSize: '200% 100%',
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    color: 'transparent',
    animationDuration: `${speed}s`,
  };
  return (
    <span
      className={cn('inline-block animate-gradient-pan motion-reduce:animate-none', className)}
      style={style}
    >
      {children}
    </span>
  );
}
