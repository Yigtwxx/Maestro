import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { domainColor } from '@/lib/agent-colors';
import { moduleColor, type ModuleKey } from '@/lib/module-colors';
import type { TaskStatus } from '@/types';

const statusStyles: Record<string, string> = {
  pending: 'border-border-bright bg-surface-2 text-muted',
  running: 'border-accent/40 bg-accent-dim text-accent',
  needs_review: 'border-amber-400/40 bg-amber-400/10 text-amber-300',
  awaiting_answer: 'border-accent/40 bg-accent-dim text-accent',
  completed: 'border-success/40 bg-success-dim text-success',
  completed_with_warnings: 'border-warning/40 bg-warning-dim text-warning',
  failed: 'border-danger/40 bg-danger-dim text-danger',
  cancelled: 'border-warning/40 bg-warning-dim text-warning',
  timeout: 'border-orange-400/40 bg-orange-400/10 text-orange-300',
};

/**
 * Status hue only — no animation. Exported so the architect task rail can paint
 * both its dots and the rope segments between them from the same palette the
 * badges use; a pulsing hairline would be noise.
 */
export const STATUS_DOT: Record<string, string> = {
  pending: 'bg-muted',
  running: 'bg-accent',
  needs_review: 'bg-amber-300',
  awaiting_answer: 'bg-accent',
  completed: 'bg-success',
  completed_with_warnings: 'bg-warning',
  failed: 'bg-danger',
  cancelled: 'bg-warning',
  timeout: 'bg-orange-300',
};

/**
 * The same hues as STATUS_DOT, as "r g b" triplets for `rgb(var(--x) / a)` —
 * the shape every other dynamic color in this app is passed to CSS in.
 * MUST stay in lockstep with STATUS_DOT: a badge and a task-rail dot for the
 * same status have to be the same color.
 */
export const STATUS_RGB: Record<string, string> = {
  pending: '139 143 163', //                muted       #8b8fa3
  running: '34 211 238', //                 accent      #22d3ee
  needs_review: '252 211 77', //            amber-300   #fcd34d
  awaiting_answer: '34 211 238',
  completed: '46 230 166', //               success     #2ee6a6
  completed_with_warnings: '255 122 69', // warning     #ff7a45
  failed: '255 77 109', //                  danger      #ff4d6d
  cancelled: '255 122 69',
  timeout: '253 186 116', //                orange-300  #fdba74
};

/** Statuses whose dot pulses because the task is still moving. */
const LIVE_STATUSES = new Set(['running', 'awaiting_answer']);

/** Dot classes for a status, falling back to the neutral hue. */
export function statusDotClass(status: string): string {
  const color = STATUS_DOT[status] ?? 'bg-muted';
  return LIVE_STATUSES.has(status) ? `${color} animate-pulse-glow` : color;
}

/** Status hue as an "r g b" triplet, falling back to the neutral hue. */
export function statusRgb(status: string): string {
  return STATUS_RGB[status] ?? STATUS_RGB.pending;
}

/** Whether a status should pulse — asked directly instead of parsing classes. */
export function isLiveStatus(status: string): boolean {
  return LIVE_STATUSES.has(status);
}

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
  const showDot = dot || Boolean(dc) || Boolean(mc) || Boolean(status && STATUS_DOT[status]);
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
            dc ? dc.dot : mc ? mc.bgSolid : status ? statusDotClass(status) : 'bg-current',
          )}
          aria-hidden
        />
      )}
      {children ?? status}
    </span>
  );
}
