'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { ArrowRight } from 'lucide-react';
import { useAuthStore } from '@/stores/auth';
import HeroConstellation from '@/components/landing/HeroConstellation';
import LandingNav from '@/components/landing/LandingNav';
import { GradientText } from '@/components/effects/GradientText';
import { buttonVariants } from '@/components/ui/Button';
import { cn } from '@/lib/cn';

// WebGL fluid sim is heavy — split it out of the initial bundle, client-only.
const SplashCursor = dynamic(() => import('@/components/SplashCursor'), { ssr: false });

// Detect the reduced-motion preference (WebGL fluid sim is GPU-heavy; skip it).
function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export default function HomePage() {
  const hydrate = useAuthStore((s) => s.hydrate);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  // Splash cursor mounts client-side only, and never under reduced motion.
  const [cursorEnabled, setCursorEnabled] = useState(false);

  useEffect(() => {
    hydrate();
    setCursorEnabled(!prefersReducedMotion());
  }, [hydrate]);

  const signedIn = hydrated && isAuthenticated;

  return (
    <main className="relative h-screen overflow-hidden bg-background">
      {/* Rainbow fluid cursor — fixed full-screen canvas behind all content (z-0). */}
      {cursorEnabled && <SplashCursor RAINBOW_MODE BACK_COLOR={{ r: 0, g: 0, b: 0 }} />}

      {/* Public top bar: brand mark on the left; GitHub, Sponsor and the auth
          entry points on the right. Fixed at top (z-20) above the hero (z-10). */}
      <LandingNav hydrated={hydrated} isAuthenticated={isAuthenticated} />

      {/* Cinematic hero: the agent constellation fills the screen; a slim CTA
          strip anchors the bottom. z-10 keeps everything above the fluid canvas. */}
      <section className="absolute inset-0 z-10">
        <HeroConstellation />

        <div className="pointer-events-none absolute inset-x-0 bottom-8 flex flex-col items-center gap-4 px-5 text-center sm:bottom-12">
          {/* Word-by-word blur-in, synced to land as the constellation settles. */}
          <HeroTagline />

          <div
            className="pointer-events-auto flex flex-wrap items-center justify-center gap-3 animate-word-in motion-reduce:animate-none"
            style={{ animationDelay: '1.1s' }}
          >
            {signedIn ? (
              <GlowingCta>
                <Link
                  href="/architect"
                  className={cn(buttonVariants({ variant: 'lime' }), 'relative gap-1.5 px-6 py-2.5')}
                >
                  Go to Panel
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </GlowingCta>
            ) : (
              <>
                <GlowingCta>
                  <Link
                    href="/register"
                    className={cn(buttonVariants({ variant: 'lime' }), 'relative gap-1.5 px-6 py-2.5')}
                  >
                    Start for Free
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </Link>
                </GlowingCta>
                <Link
                  href="/login"
                  className={cn(buttonVariants({ variant: 'lime-outline' }), 'px-6 py-2.5')}
                >
                  Sign In
                </Link>
              </>
            )}
          </div>
        </div>
      </section>

    </main>
  );
}

// Tagline split into plain / gradient-highlighted word runs so each word can
// blur in on its own beat while the key phrase carries the brand sweep.
const TAGLINE_PRE = ['Multi-layer'] as const;
const TAGLINE_GRADIENT = ['AI', 'agent', 'orchestration'] as const;
const TAGLINE_POST = ['—', 'enter', 'a', 'single', 'prompt,', 'automate', 'end', 'to', 'end.'] as const;
const TAGLINE_START_S = 0.9; // syncs with the constellation fly-in settling
const TAGLINE_STEP_S = 0.05;

/** Word-by-word blur-in tagline with a gradient-swept key phrase. */
function HeroTagline() {
  let wordIndex = 0;
  const wordProps = () => ({
    className: 'inline-block animate-word-in motion-reduce:animate-none',
    style: { animationDelay: `${(TAGLINE_START_S + wordIndex++ * TAGLINE_STEP_S).toFixed(2)}s` },
  });
  return (
    <p className="max-w-xl font-mono text-xs leading-relaxed text-muted sm:text-sm">
      {TAGLINE_PRE.map((w) => (
        <span key={w} {...wordProps()}>
          {w}&nbsp;
        </span>
      ))}
      {TAGLINE_GRADIENT.map((w) => (
        <span key={w} {...wordProps()}>
          <GradientText className="font-semibold">{w}</GradientText>&nbsp;
        </span>
      ))}
      {TAGLINE_POST.map((w) => (
        <span key={w} {...wordProps()}>
          {w}&nbsp;
        </span>
      ))}
    </p>
  );
}

/** Breathing lime halo behind the primary CTA. */
function GlowingCta({ children }: { children: React.ReactNode }) {
  return (
    <span className="relative inline-flex">
      <span
        aria-hidden
        className="absolute inset-0 rounded-md bg-primary/40 blur-md animate-pulse-glow motion-reduce:hidden"
      />
      {children}
    </span>
  );
}
