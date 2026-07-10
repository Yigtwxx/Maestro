import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { domainColor } from '@/lib/agent-colors';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';
import type { TaskStatus } from '@/types';

const statusStyles: Record<string, string> = {
  pending: 'border-border-bright bg-surface-2 text-muted',
  running: 'border-accent/40 bg-accent-dim text-accent',
  needs_review: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  completed: 'border-primary/40 bg-primary-dim text-primary',
  failed: 'border-danger/40 bg-danger-dim text-danger',
  cancelled: 'border-border-bright bg-surface-2 text-muted',
  timeout: 'border-orange-400/40 bg-orange-400/10 text-orange-300',
};

const statusDot: Record<string, string> = {
  pending: 'bg-muted',
  running: 'bg-accent animate-pulse-glow',
  needs_review: 'bg-amber-300',
  completed: 'bg-primary',
  failed: 'bg-danger',
  cancelled: 'bg-muted',
  timeout: 'bg-orange-300',
};

/** Marketplace/integration chip tones: CONNECTED (lime), READY (cyan), PENDING (gray). */
type BadgeTone = 'lime' | 'cyan' | 'gray' | 'danger';

const toneStyles: Record<BadgeTone, string> = {
  lime: 'border-primary bg-primary text-black',
  cyan: 'border-accent/40 bg-accent-dim text-accent',
  gray: 'border-border-bright bg-surface-2 text-muted',
  danger: 'border-danger/40 bg-danger-dim text-danger',
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status?: TaskStatus | string;
  tone?: BadgeTone;
  /** Per-domain neon chip (border + dim fill + text + dot). */
  domain?: string;
  /** Per-module neon chip; `domain` wins when both are set. */
  module?: ModuleKey;
  dot?: boolean;
}

export function Badge({
  status,
  tone,
  domain,
  module,
  dot,
  className,
  children,
  ...props
}: BadgeProps) {
  const dc = domain ? domainColor(domain) : undefined;
  const mc = !dc && module ? moduleColor(module) : undefined;
  const styles = dc
    ? cn(dc.border, dc.bg, dc.text)
    : mc
      ? cn(mc.border, mc.bg, mc.text)
      : tone
        ? toneStyles[tone]
        : status
          ? (statusStyles[status] ?? 'border-border-bright bg-surface-2 text-muted')
          : 'border-border-bright bg-surface-2 text-muted';
  const showDot = dot || Boolean(dc) || Boolean(mc) || Boolean(status && statusDot[status]);
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-micro',
        styles,
        className,
      )}
      {...props}
    >
      {showDot && (
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            dc ? dc.dot : mc ? mc.bgSolid : status ? (statusDot[status] ?? 'bg-muted') : 'bg-current',
          )}
          aria-hidden
        />
      )}
      {children ?? status}
    </span>
  );
}
