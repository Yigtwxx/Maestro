'use client';

import type { CSSProperties } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bell, Settings } from 'lucide-react';
import { ADMIN_LINK, NAV } from '@/components/layout/Sidebar';
import { moduleColor, moduleFromPathname } from '@/lib/module-colors';

export function TopBar() {
  const pathname = usePathname();
  const current = [...NAV, ADMIN_LINK].find((item) => pathname.startsWith(item.href));
  const moduleKey = moduleFromPathname(pathname);
  const mc = moduleColor(moduleKey);
  const label = current?.label ?? 'Settings';

  return (
    <header className="relative flex h-14 shrink-0 items-center justify-between border-b border-border bg-surface px-6">
      {/* One-shot module-tinted light pan along the bottom edge per navigation. */}
      <span
        key={moduleKey}
        aria-hidden
        className="topbar-pan pointer-events-none absolute inset-x-0 -bottom-px h-px"
        style={{ ['--tb-rgb' as string]: mc.rgb } as CSSProperties}
      />
      <span className="text-micro text-muted">
        MAESTRO <span className="text-border-bright">/</span>{' '}
        {/* Keyed remount crossfades the section label on navigation. */}
        <span
          key={label}
          className={`inline-block animate-word-in motion-reduce:animate-none ${mc.text}`}
        >
          {label}
        </span>
      </span>
      <div className="flex items-center gap-4">
        <button
          className="text-muted transition-colors hover:text-white"
          aria-label="Notifications"
        >
          <Bell className="h-4 w-4" />
        </button>
        <Link
          href="/settings/api-keys"
          className="text-muted transition-colors hover:text-white"
          aria-label="Settings"
        >
          <Settings className="h-4 w-4" />
        </Link>
        <span className="flex items-center gap-2 rounded border border-success/40 bg-success-dim px-2.5 py-1 text-micro text-success">
          <span className="relative flex h-1.5 w-1.5" aria-hidden>
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60 motion-reduce:hidden" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
          </span>
          System Live
        </span>
      </div>
    </header>
  );
}
