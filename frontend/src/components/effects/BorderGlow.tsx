'use client';

// Adapted from React Bits "Border Glow" (BorderGlow-TS-TW,
// https://reactbits.dev/components/border-glow) — simplified to a single-hue
// arc that follows the cursor along the card edge. The original's mesh
// gradients and wrapper card are dropped so this renders as a pure overlay
// inside the existing Card; the hue comes from the module/domain rgb triplet.
//
// The layer is a `span`, not a `div`, so it is also valid inside the
// `<button>`-based cards (agent catalog). Absolute positioning blockifies it,
// so the rendered result is identical either way.

import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/lib/motion';

interface BorderGlowProps {
  /** Space-separated RGB triplet, e.g. "34 211 238". */
  rgb: string;
  /** Edge proximity (0-1) where the glow starts appearing. */
  sensitivity?: number;
  /**
   * Scales the arc's line weight, its angular width and the bloom around it.
   * `1` is the restrained default used by content cards; raise it where the
   * card is the primary thing being chosen and the glow has to read clearly.
   */
  intensity?: number;
}

/** Line weight, arc width and bloom radius at `intensity = 1`. */
const BASE_THICKNESS_PX = 1;
const BASE_ARC_DEG = 60;
const BASE_BLOOM_PX = 8;
const BASE_BLOOM_ALPHA = 0.6;

/**
 * Cursor-proximity border glow. Mount inside a `relative` parent with a
 * border radius; pointer tracking attaches to the parent, so the layer never
 * intercepts events and the host component stays server-safe. Writes CSS
 * vars directly (no re-renders per pointer move).
 */
export function BorderGlow({
  rgb,
  sensitivity = 0.35,
  intensity = 1,
}: BorderGlowProps) {
  const ref = useRef<HTMLSpanElement>(null);
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
  // Arc width is capped so a high intensity cannot wrap it into a solid ring.
  const arc = Math.min(BASE_ARC_DEG * intensity, 150);
  const bloomAlpha = Math.min(BASE_BLOOM_ALPHA * intensity, 1);
  // `--bg-angle` is measured from east (atan2) while a conic gradient starts at
  // north, and the gradient peaks `arc` degrees after its start — so the start
  // offset that lands the peak on the cursor is `90 - arc`.
  const startOffset = 90 - arc;
  return (
    <span
      ref={ref}
      aria-hidden
      className="pointer-events-none absolute -inset-px rounded-[inherit]"
      style={{
        ['--bg-angle' as string]: '45deg',
        ['--bg-opacity' as string]: '0',
        padding: `${BASE_THICKNESS_PX * intensity}px`,
        background: `conic-gradient(from calc(var(--bg-angle) + ${startOffset}deg), transparent 0deg, rgb(${rgb}) ${arc}deg, transparent ${arc * 2}deg 360deg)`,
        WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
        WebkitMaskComposite: 'xor',
        mask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
        maskComposite: 'exclude',
        filter: `drop-shadow(0 0 ${BASE_BLOOM_PX * intensity}px rgb(${rgb} / ${bloomAlpha}))`,
        opacity: 'var(--bg-opacity)',
        transition: 'opacity 0.3s ease-out',
      }}
    />
  );
}
