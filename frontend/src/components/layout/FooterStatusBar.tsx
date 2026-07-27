'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ADMIN_LINK, NAV } from '@/components/layout/Sidebar';

const SEPARATOR = <span className="mx-2 text-border-bright">|</span>;

export function FooterStatusBar() {
  const pathname = usePathname();
  // Mirror the TopBar section resolution so the footer names the active module.
  const current = [...NAV, ADMIN_LINK].find((item) => pathname.startsWith(item.href));
  const section = (current?.label ?? 'Orchestration Layer').toUpperCase();

  return (
    <footer className="flex h-9 shrink-0 items-center justify-between border-t border-border bg-surface px-6">
      <span className="text-micro text-muted">
        © 2026 MAESTRO —{' '}
        {/* Keyed remount crossfades the section label on navigation. */}
        <span key={section} className="inline-block animate-word-in motion-reduce:animate-none">
          {section}
        </span>
      </span>
      <span className="text-micro flex items-center text-muted">
        <Link href="/legal" className="transition-colors hover:text-white">
          Legal
        </Link>
        {SEPARATOR}
        <Link href="/privacy" className="transition-colors hover:text-white">
          Privacy
        </Link>
      </span>
    </footer>
  );
}
