// Adapted from React Bits "Shiny Text" (ShinyText-TS-TW,
// https://reactbits.dev/text-animations/shiny-text) — the original drives the
// sweep with a persistent rAF loop via motion; this version is pure CSS
// (`shine-sweep` keyframe), server-safe, and inert under reduced motion.

import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface ShinyTextProps {
  children: ReactNode;
  className?: string;
  /** Sweep duration in seconds. */
  speed?: number;
  /** Base text color. */
  color?: string;
  /** Highlight color sweeping across. */
  shineColor?: string;
}

/** Metallic sheen sweeping across text. */
export function ShinyText({
  children,
  className,
  speed = 3,
  color = '#8b8fa3',
  shineColor = '#ffffff',
}: ShinyTextProps) {
  const style: CSSProperties = {
    backgroundImage: `linear-gradient(120deg, ${color} 40%, ${shineColor} 50%, ${color} 60%)`,
    backgroundSize: '200% auto',
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
    color: 'transparent',
    animationDuration: `${speed}s`,
  };
  return (
    <span
      className={cn('inline-block animate-shine-sweep motion-reduce:animate-none', className)}
      style={style}
    >
      {children}
    </span>
  );
}
