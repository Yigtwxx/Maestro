'use client';

// Adapted from React Bits "Border Glow" (BorderGlow-TS-TW,
// https://reactbits.dev/components/border-glow) — simplified to a single-hue
// arc that follows the cursor along the card edge. The original's mesh
// gradients and wrapper card are dropped so this renders as a pure overlay
// inside the existing Card; the hue comes from the module/domain rgb triplet.

import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/lib/motion';

interface BorderGlowProps {
  /** Space-separated RGB triplet, e.g. "34 211 238". */
  rgb: string;
  /** Edge proximity (0-1) where the glow starts appearing. */
  sensitivity?: number;
}

/**
 * Cursor-proximity border glow. Mount inside a `relative` parent with a
 * border radius; pointer tracking attaches to the parent, so the layer never
 * intercepts events and the host component stays server-safe. Writes CSS
 * vars directly (no re-renders per pointer move).
 */
export function BorderGlow({ rgb, sensitivity = 0.35 }: BorderGlowProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) return;
    const layer = ref.current;
    const parent = layer?.parentElement;
    if (!layer || !parent) return;

    const onMove = (e: PointerEvent) => {
      const rect = parent.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const dx = e.clientX - rect.left - cx;
      const dy = e.clientY - rect.top - cy;
      const proximity = Math.min(Math.max(Math.abs(dx) / cx, Math.abs(dy) / cy), 1);
      const opacity = Math.max(0, (proximity - sensitivity) / (1 - sensitivity));
      let angle = Math.atan2(dy, dx) * (180 / Math.PI);
      if (angle < 0) angle += 360;
      layer.style.setProperty('--bg-angle', `${angle.toFixed(1)}deg`);
      layer.style.setProperty('--bg-opacity', opacity.toFixed(3));
    };
    const onLeave = () => layer.style.setProperty('--bg-opacity', '0');

    parent.addEventListener('pointermove', onMove);
    parent.addEventListener('pointerleave', onLeave);
    return () => {
      parent.removeEventListener('pointermove', onMove);
      parent.removeEventListener('pointerleave', onLeave);
    };
  }, [reduced, sensitivity]);

  if (reduced) return null;
  return (
    <div
      ref={ref}
      aria-hidden
      className="pointer-events-none absolute -inset-px rounded-[inherit]"
      style={{
        ['--bg-angle' as string]: '45deg',
        ['--bg-opacity' as string]: '0',
        padding: '1px',
        background: `conic-gradient(from calc(var(--bg-angle) + 30deg), transparent 0deg, rgb(${rgb}) 60deg, transparent 120deg 360deg)`,
        WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
        WebkitMaskComposite: 'xor',
        mask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
        maskComposite: 'exclude',
        filter: `drop-shadow(0 0 8px rgb(${rgb} / 0.6))`,
        opacity: 'var(--bg-opacity)',
        transition: 'opacity 0.3s ease-out',
      }}
    />
  );
}
