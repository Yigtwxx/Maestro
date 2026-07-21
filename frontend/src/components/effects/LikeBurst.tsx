'use client';

// An X (Twitter)-style "like" micro-interaction for the Sponsor button: on
// hover the heart fills and pops while a small burst of two-tone particles
// flies outward and fades. Structural pattern mirrors BorderGlow — a
// pointer-events-none overlay inside a positioned host, listeners attached to
// the parent element so the whole button is the hover target and the link
// stays clickable. Kept deliberately restrained (no rainbow confetti).

import { useEffect, useRef, useState } from 'react';
import { Heart } from 'lucide-react';
import { useReducedMotion } from '@/lib/motion';
import { cn } from '@/lib/cn';

/** Sponsor pink `#db61a2` and brand champagne `#d3cbc0` as CSS rgb triplets. */
const SPONSOR_RGB = '219 97 162';
const CHAMPAGNE_RGB = '211 203 192';
/** Share of particles tinted sponsor-pink; the rest are champagne. */
const PINK_RATIO = 0.6;
/** Outward travel range (px) and dot size range (px) for the burst. */
const MIN_DISTANCE = 14;
const DISTANCE_SPREAD = 12;
const MIN_SIZE = 3;
const SIZE_SPREAD = 3;
/** Per-particle start scatter (s) so the burst doesn't fire as one rigid ring. */
const MAX_DELAY = 0.04;
/** Restrained default — tasteful pop, not confetti. */
const DEFAULT_COUNT = 12;

interface Particle {
  id: number;
  /** Signed offsets from the emitter centre, in px. */
  tx: number;
  ty: number;
  size: number;
  /** Space-separated rgb triplet fed into `rgb(...)`. */
  rgb: string;
  delay: number;
}

/** Build a fresh burst. Runs client-side (in the hover handler) only, so the
 * randomness never reaches SSR and cannot cause a hydration mismatch. */
function makeParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, id) => {
    const angle = Math.random() * Math.PI * 2;
    const distance = MIN_DISTANCE + Math.random() * DISTANCE_SPREAD;
    return {
      id,
      tx: Math.cos(angle) * distance,
      ty: Math.sin(angle) * distance,
      size: MIN_SIZE + Math.random() * SIZE_SPREAD,
      rgb: Math.random() < PINK_RATIO ? SPONSOR_RGB : CHAMPAGNE_RGB,
      delay: Math.random() * MAX_DELAY,
    };
  });
}

interface LikeBurstProps {
  /** Particles emitted per hover. Kept modest (8–14) for restraint. */
  count?: number;
  /** Classes for the heart glyph (sizing/colour). */
  className?: string;
}

/**
 * Renders the heart icon plus its like-burst overlay. Mount it as a direct
 * child of the interactive element (e.g. the Sponsor `<a>`): it listens for
 * `mouseenter` on `parentElement`, so hovering anywhere on the button replays
 * the burst. Purely decorative (`aria-hidden`); the accessible name comes from
 * the host's own text. Disabled under `prefers-reduced-motion`.
 */
export function LikeBurst({ count = DEFAULT_COUNT, className }: LikeBurstProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  const [burst, setBurst] = useState(0);
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    if (reduced) return;
    const host = ref.current?.parentElement;
    if (!host) return;
    const onEnter = () => {
      setParticles(makeParticles(count));
      // A new key remounts the animated nodes, restarting the CSS animation
      // from frame 0 on every re-entry — cleaner than a reflow restart hack.
      setBurst((b) => b + 1);
    };
    host.addEventListener('mouseenter', onEnter);
    return () => host.removeEventListener('mouseenter', onEnter);
  }, [reduced, count]);

  if (reduced) {
    return <Heart aria-hidden className={cn('h-4 w-4', className)} />;
  }

  return (
    <span ref={ref} className="relative inline-flex">
      {/* Base outline heart — always visible. */}
      <Heart aria-hidden className={cn('h-4 w-4 text-sponsor', className)} />
      {/* Filled heart that pops and fades over the base on each burst. */}
      <Heart
        key={`heart-${burst}`}
        aria-hidden
        fill="currentColor"
        className={cn(
          'pointer-events-none absolute inset-0 h-4 w-4 text-sponsor like-heart-pop',
          burst === 0 && 'opacity-0',
          className,
        )}
      />
      {/* Zero-size emitter at the heart centre; particles radiate from here. */}
      <span
        key={`burst-${burst}`}
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 h-0 w-0"
      >
        {particles.map((p) => (
          <span
            key={p.id}
            className="like-particle absolute rounded-full"
            style={{
              width: p.size,
              height: p.size,
              background: `rgb(${p.rgb})`,
              animationDelay: `${p.delay}s`,
              ['--tx' as string]: `${p.tx}px`,
              ['--ty' as string]: `${p.ty}px`,
            }}
          />
        ))}
      </span>
    </span>
  );
}
