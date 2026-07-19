'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { useAuthStore } from '@/stores/auth';
import LandingNav from '@/components/landing/LandingNav';
import RayLights from '@/components/effects/RayLights';
import { GradientText } from '@/components/effects/GradientText';
import { BrandMark } from '@/components/brand/BrandMark';
import { LandingFeatures } from '@/components/landing/LandingFeatures';
import { LandingMetrics } from '@/components/landing/LandingMetrics';
import { MarketingFooter } from '@/components/landing/MarketingFooter';
import { LandingScrollStage } from '@/components/landing/LandingScrollStage';
import { buttonVariants } from '@/components/ui/Button';
import { cn } from '@/lib/cn';

export default function HomePage() {
  const hydrate = useAuthStore((s) => s.hydrate);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const signedIn = hydrated && isAuthenticated;

  // Hero content for the first panel; the stage owns the full-viewport frame
  // and vertical centering around it.
  const hero = (
    <div className="flex flex-col items-center">
      <Wordmark />

      <HeroTagline />

      <div
        className="mt-8 flex flex-wrap items-center justify-center gap-3 animate-word-in motion-reduce:animate-none"
        style={{ animationDelay: '0.9s' }}
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
                Get started
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
  );

  // Second panel: wide sections + footer, scrolling on their own once the stage
  // slides down to them. A flex spacer absorbs any extra height between the
  // features and the metrics, so the metrics strip stays anchored directly on
  // top of the footer at the bottom edge instead of floating mid-panel.
  const below = (
    <div className="flex min-h-full flex-col">
      <LandingFeatures />
      <div className="flex-1" aria-hidden />
      <LandingMetrics />
      <MarketingFooter />
    </div>
  );

  return (
    <main className="relative h-[100svh] overflow-hidden bg-background">
      {/* Light rays pinned to the viewport (z-0, behind everything). Keeping the
          canvas viewport-sized preserves the beam proportions; because it is
          fixed, every panel that slides beneath it is lit from the top. */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <RayLights />
      </div>

      {/* Public top bar (z-20, fixed). */}
      <LandingNav hydrated={hydrated} isAuthenticated={isAuthenticated} />

      {/* Hero -> below content, as two scroll-hijacked panels (z-10). */}
      <LandingScrollStage hero={hero} below={below} />
    </main>
  );
}

/** Large brand lockup: the Maestro monogram beside the wordmark. */
function Wordmark() {
  return (
    <div
      className="flex items-center gap-4 animate-word-in motion-reduce:animate-none"
      style={{ animationDelay: '0.3s' }}
    >
      <BrandMark
        className="h-14 w-14 rounded-lg sm:h-16 sm:w-16"
        glyphClassName="h-8 w-8 sm:h-9 sm:w-9"
      />
      <span className="text-5xl font-semibold leading-none tracking-tight text-foreground sm:text-6xl">
        Maestro
      </span>
    </div>
  );
}

// Tagline split into plain / gradient-highlighted word runs so each word can
// blur in on its own beat while the key phrase carries the brand sweep.
const TAGLINE_PRE = ['Multi-layer'] as const;
const TAGLINE_GRADIENT = ['AI', 'agent', 'orchestration'] as const;
const TAGLINE_POST = ['—', 'enter', 'a', 'single', 'prompt,', 'automate', 'end', 'to', 'end.'] as const;
const TAGLINE_START_S = 0.5; // lands just after the wordmark settles
const TAGLINE_STEP_S = 0.04;

/** Word-by-word blur-in tagline with a gradient-swept key phrase. */
function HeroTagline() {
  let wordIndex = 0;
  const wordProps = () => ({
    className: 'inline-block animate-word-in motion-reduce:animate-none',
    style: { animationDelay: `${(TAGLINE_START_S + wordIndex++ * TAGLINE_STEP_S).toFixed(2)}s` },
  });
  return (
    <p className="mt-6 max-w-xl font-mono text-sm leading-relaxed text-muted sm:text-base">
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

/** Breathing periwinkle halo behind the primary CTA. */
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
