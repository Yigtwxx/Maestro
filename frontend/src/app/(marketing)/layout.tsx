'use client';

import { useEffect } from 'react';
import type { ReactNode } from 'react';
import LandingNav from '@/components/landing/LandingNav';
import { MarketingFooter } from '@/components/landing/MarketingFooter';
import { useAuthStore } from '@/stores/auth';

/**
 * Shell for the public marketing tabs. Unlike `(app)`, it never redirects: these
 * pages must render for anonymous visitors. Auth state is read only to decide
 * which call-to-action the nav shows.
 *
 * Scrollable and WebGL-free by design — the fluid cursor and the constellation
 * belong to `/` alone, which keeps the one-heavy-canvas-per-screen budget.
 */
export default function MarketingLayout({ children }: { children: ReactNode }) {
  const hydrate = useAuthStore((s) => s.hydrate);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <LandingNav hydrated={hydrated} isAuthenticated={isAuthenticated} />
      {/* Clears the fixed nav bar. */}
      <main className="flex-1 pt-20">{children}</main>
      <MarketingFooter />
    </div>
  );
}
