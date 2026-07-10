'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowRight, Heart } from 'lucide-react';
import { buttonVariants } from '@/components/ui/Button';
import { GITHUB_SPONSORS_URL, GITHUB_URL, MARKETING_NAV_LINKS } from '@/lib/constants';
import { cn } from '@/lib/cn';

// lucide-react dropped brand marks, so the GitHub glyph is inlined here.
function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M12 .5A11.5 11.5 0 0 0 .5 12a11.5 11.5 0 0 0 7.86 10.92c.575.106.785-.25.785-.556 0-.274-.01-1-.015-1.965-3.196.695-3.87-1.54-3.87-1.54-.523-1.33-1.277-1.684-1.277-1.684-1.044-.714.08-.7.08-.7 1.155.082 1.763 1.186 1.763 1.186 1.026 1.758 2.692 1.25 3.348.956.104-.744.402-1.25.73-1.538-2.552-.29-5.236-1.276-5.236-5.68 0-1.255.448-2.28 1.184-3.084-.12-.29-.513-1.46.112-3.043 0 0 .966-.31 3.165 1.178a10.98 10.98 0 0 1 2.88-.388c.977.004 1.96.132 2.88.388 2.197-1.488 3.162-1.178 3.162-1.178.627 1.583.233 2.753.114 3.043.737.804 1.183 1.829 1.183 3.084 0 4.415-2.688 5.386-5.25 5.67.413.356.78 1.058.78 2.133 0 1.54-.014 2.782-.014 3.16 0 .308.207.668.79.554A11.5 11.5 0 0 0 23.5 12 11.5 11.5 0 0 0 12 .5Z" />
    </svg>
  );
}

interface LandingNavProps {
  /** Auth state has been resolved (avoids rendering the wrong CTA on first paint). */
  hydrated: boolean;
  isAuthenticated: boolean;
}

/**
 * Top bar for the public pages: brand mark, the marketing tabs, then GitHub,
 * Sponsor and the auth entry points. Guests get Sign In/Sign Up; a signed-in
 * visitor gets a single "Go to Panel" shortcut into the app.
 *
 * The tab strip stays lime: it is chrome, and lime is the brand hue. Per-module
 * neon belongs to the pages themselves, not to the bar above them.
 */
export default function LandingNav({ hydrated, isAuthenticated }: LandingNavProps) {
  const pathname = usePathname();

  return (
    <header
      className="fixed inset-x-0 top-0 z-20 border-b border-border/60 bg-background/70 backdrop-blur-md animate-word-in motion-reduce:animate-none"
      style={{ animationDelay: '0.3s' }}
    >
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
        <Link href="/" className="flex shrink-0 items-center gap-3" aria-label="Maestro">
          <span
            className="flex h-9 w-9 items-center justify-center rounded bg-primary text-black"
            aria-hidden
          >
            {/* Maestro monogram: an "M" traced as two peaks and a valley — a nod
                to the orchestrator → agents → reviewer flow. */}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2.4}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-5 w-5"
            >
              <path d="M5 17V7l7 6 7-6v10" />
            </svg>
          </span>
          <span className="hidden font-sans text-sm font-bold tracking-wide text-white sm:block">
            MAESTRO
            <span className="text-micro ml-2 text-primary">AI OS</span>
          </span>
        </Link>

        {/* Tab strip with an animated underline indicator. On narrow screens it
            scrolls horizontally rather than collapsing into a drawer. */}
        <div className="scrollbar-none mx-3 flex min-w-0 flex-1 items-center gap-5 overflow-x-auto sm:mx-6 sm:justify-center sm:gap-7">
          {MARKETING_NAV_LINKS.map((link) => {
            const active = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'relative shrink-0 py-1 font-mono text-xs uppercase tracking-wide transition-colors focus-visible:outline-none',
                  'after:absolute after:-bottom-0.5 after:left-0 after:h-px after:w-full after:origin-left after:bg-primary after:transition-transform after:duration-300',
                  active
                    ? 'text-white after:scale-x-100'
                    : 'text-muted after:scale-x-0 hover:text-white hover:after:scale-x-100 focus-visible:text-white focus-visible:after:scale-x-100',
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </div>

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub"
            className={cn(buttonVariants({ variant: 'ghost' }), 'px-2.5')}
          >
            <GithubIcon className="h-4 w-4" />
            <span className="hidden sm:inline">GitHub</span>
          </a>

          {/* Hidden on narrow screens so the tab strip keeps its room; the
              footer still carries a Sponsor link. */}
          <a
            href={GITHUB_SPONSORS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              buttonVariants({ variant: 'sponsor-outline' }),
              'hidden gap-1.5 sm:inline-flex',
            )}
          >
            <Heart className="h-4 w-4" aria-hidden />
            Sponsor
          </a>

          <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden />

          {hydrated && isAuthenticated ? (
            <Link href="/architect" className={cn(buttonVariants({ variant: 'lime' }), 'gap-1.5')}>
              Go to Panel
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className={cn(buttonVariants({ variant: 'ghost' }), 'hidden sm:inline-flex')}
              >
                Sign In
              </Link>
              <Link href="/register" className={buttonVariants({ variant: 'lime' })}>
                Sign Up
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
