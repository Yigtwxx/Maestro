import Link from 'next/link';
import type { ReactNode } from 'react';
import { Heart } from 'lucide-react';
import { GITHUB_SPONSORS_URL, GITHUB_URL, MARKETING_NAV_LINKS } from '@/lib/constants';
import { LEGAL_FOOTER_LINKS } from '@/lib/legal';

const FOUNDING_YEAR = 2026;

const LINK_CLASS =
  'font-mono text-xs uppercase tracking-wide text-muted transition-colors hover:text-white';

function FooterColumn({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav className="flex flex-col gap-2" aria-label={label}>
      <span className="text-micro text-slate-400">{label}</span>
      {children}
    </nav>
  );
}

/**
 * Closing bar for the public marketing pages. Both link groups come from their
 * source arrays -- `MARKETING_NAV_LINKS` and the legal registry -- so the footer
 * can never drift from the tab strip above it or from the documents themselves.
 */
export function MarketingFooter() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="mx-auto flex max-w-7xl flex-col gap-10 px-5 py-10 sm:px-8 md:flex-row md:justify-between">
        <div>
          <Link href="/" className="flex items-center gap-2.5" aria-label="Maestro">
            <span
              className="flex h-7 w-7 items-center justify-center rounded bg-primary text-black"
              aria-hidden
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2.4}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
              >
                <path d="M5 17V7l7 6 7-6v10" />
              </svg>
            </span>
            <span className="font-sans text-sm font-bold tracking-wide text-white">
              MAESTRO
            </span>
          </Link>
          <p className="mt-3 font-mono text-xs text-muted">
            © {FOUNDING_YEAR} Maestro — multi-layer AI agent orchestration.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-x-10 gap-y-8 sm:grid-cols-3">
          <FooterColumn label="Product">
            {MARKETING_NAV_LINKS.map((link) => (
              <Link key={link.href} href={link.href} className={LINK_CLASS}>
                {link.label}
              </Link>
            ))}
          </FooterColumn>

          <FooterColumn label="Legal">
            {LEGAL_FOOTER_LINKS.map((link) => (
              <Link key={link.href} href={link.href} className={LINK_CLASS}>
                {link.label}
              </Link>
            ))}
          </FooterColumn>

          <FooterColumn label="Community">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={LINK_CLASS}
            >
              GitHub
            </a>
            <a
              href={GITHUB_SPONSORS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 font-mono text-xs uppercase tracking-wide text-muted transition-colors hover:text-sponsor"
            >
              <Heart className="h-3.5 w-3.5" aria-hidden />
              Sponsor
            </a>
          </FooterColumn>
        </div>
      </div>
    </footer>
  );
}
