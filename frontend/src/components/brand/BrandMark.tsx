'use client';

import { useId } from 'react';
import { MONOGRAM_GRADIENT, MONOGRAM_PATH, MONOGRAM_STROKE_WIDTH } from '@/lib/seo/config';
import { cn } from '@/lib/cn';

/**
 * The shared `MONOGRAM_VIEWBOX` (`0 0 24 24`) frames the signature tightly — right
 * for the favicon and satori marks. On the champagne square that tightness pushes
 * the peaks against the top edge, reading as a clipped "M". The DOM mark therefore
 * pads the viewBox to inset the glyph and recentre it on the ink's own centre
 * (~12.85, 12.3), so the peaks keep clear headroom on every surface.
 */
const PADDED_VIEWBOX = '-1.5 -2 29 29';

interface BrandMarkProps {
  /** Classes for the champagne square: sizing plus a `rounded*` corner. */
  className?: string;
  /** Classes sizing the glyph inside the square (e.g. `h-5 w-5`). */
  glyphClassName?: string;
  /** Adds the champagne glow used by the landing hero lockup. */
  glow?: boolean;
}

/**
 * The Maestro brand mark: the signature "M" on its champagne square, drawn once
 * for every DOM surface (nav, hero, footer). The navy gloss gradient lives in a
 * per-instance `<defs>` keyed by `useId()`, so several marks on one page never
 * collide on the gradient id. Satori-rendered marks use `og-monogram.tsx`.
 */
export function BrandMark({ className, glyphClassName, glow }: BrandMarkProps) {
  const gradientId = useId();
  const [top, mid, bottom] = MONOGRAM_GRADIENT;

  return (
    <span
      className={cn(
        'flex items-center justify-center bg-primary',
        glow && 'shadow-glow-primary',
        className,
      )}
      aria-hidden
    >
      <svg
        viewBox={PADDED_VIEWBOX}
        fill="none"
        strokeWidth={MONOGRAM_STROKE_WIDTH}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={glyphClassName}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={top} />
            <stop offset="50%" stopColor={mid} />
            <stop offset="100%" stopColor={bottom} />
          </linearGradient>
        </defs>
        <path d={MONOGRAM_PATH} stroke={`url(#${gradientId})`} />
      </svg>
    </span>
  );
}
