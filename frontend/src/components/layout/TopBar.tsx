'use client';

import type { CSSProperties } from 'react';
import { usePathname } from 'next/navigation';
import { Bell } from 'lucide-react';
import { ADMIN_LINK, NAV } from '@/components/layout/Sidebar';
import { STATUS_DOT } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import { TERMINAL_STATUSES } from '@/lib/constants';
import { moduleColor, moduleFromPathname } from '@/lib/module-colors';
import { useTaskStore } from '@/stores/tasks';
import type { TaskStatus } from '@/types';

// Bell tint per terminal task status, mirroring the text hues of Badge's
// `statusStyles` (the canonical status palette) so the notification cue reads as
// the same green/amber/red the task badges use.
const BELL_TONE: Partial<Record<TaskStatus, string>> = {
  completed: 'text-success',
  completed_with_warnings: 'text-warning',
  cancelled: 'text-warning',
  failed: 'text-danger',
  timeout: 'text-orange-300',
};

export function TopBar() {
  const pathname = usePathname();
  const current = [...NAV, ADMIN_LINK].find((item) => pathname.startsWith(item.href));
  const moduleKey = moduleFromPathname(pathname);
  const mc = moduleColor(moduleKey);
  const label = current?.label ?? 'Settings';

  // The active architect task's status is a global singleton, so the bell can
  // reflect its outcome from any page. Neutral until the task lands terminal.
  const status = useTaskStore((s) => s.status);
  const terminal = status !== undefined && TERMINAL_STATUSES.has(status);
  const bellTone = terminal && status ? BELL_TONE[status] : undefined;

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
          className={cn('relative transition-colors hover:text-white', bellTone ?? 'text-muted')}
          aria-label={terminal ? `Notifications — last task ${status}` : 'Notifications'}
        >
          {/* Keyed remount replays the one-shot flash each time a task lands on
              a new terminal status; running/idle leaves the bell neutral. */}
          <span
            key={terminal ? status : 'idle'}
            className={cn('block', terminal && 'animate-pop-flash motion-reduce:animate-none')}
          >
            <Bell className="h-4 w-4" />
          </span>
          {terminal && status && (
            <span className="absolute -right-0.5 -top-0.5 flex h-2 w-2" aria-hidden>
              <span
                className={cn(
                  'absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 motion-reduce:hidden',
                  STATUS_DOT[status],
                )}
              />
              <span
                className={cn('relative inline-flex h-2 w-2 rounded-full', STATUS_DOT[status])}
              />
            </span>
          )}
        </button>
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
