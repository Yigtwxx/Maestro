'use client';

import { SlidersHorizontal, Square, Terminal } from 'lucide-react';
import { cn } from '@/lib/cn';
import { MODULE_COLOR } from '@/lib/module-colors';

const mc = MODULE_COLOR.architect;

/** Characters of the prompt shown in the hover preview before it is cut. */
const PREVIEW_LEN = 60;

export type PanelKey = 'config' | 'log';

function preview(prompt: string): string {
  const trimmed = prompt.trim();
  if (!trimmed) return 'No prompt yet.';
  return trimmed.length > PREVIEW_LEN
    ? `${trimmed.slice(0, PREVIEW_LEN).trimEnd()}…`
    : trimmed;
}

interface RailFlyoutProps {
  children: React.ReactNode;
}

/**
 * Read-only summary that flies out to the LEFT of the rail (the rail is on the
 * right edge, so `right-full`). Same idiom as the task rail's hover label, and
 * the same constraint: no ancestor may clip overflow. Deliberately
 * `pointer-events-none` — every action lives on the rail itself, so the pointer
 * never has to travel into this box.
 */
function RailFlyout({ children }: RailFlyoutProps) {
  return (
    <span
      className={cn(
        'pointer-events-none absolute right-full top-2 z-20 mr-3 hidden w-64 rounded',
        'border border-border bg-surface-2 p-3 text-left text-micro text-slate-200',
        'group-hover:block group-focus-visible:block',
      )}
    >
      {children}
    </span>
  );
}

interface RailTabProps {
  label: string;
  icon: React.ReactNode;
  open: boolean;
  onClick: () => void;
  /** id of the panel this tab discloses. */
  controls: string;
  badge?: string;
  children?: React.ReactNode;
}

function RailTab({
  label,
  icon,
  open,
  onClick,
  controls,
  badge,
  children,
}: RailTabProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={open}
      aria-controls={controls}
      title={label}
      className={cn(
        'group relative flex flex-1 flex-col items-center gap-3 rounded-lg border py-4',
        'transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-module-architect',
        open
          ? cn('border-module-architect/40 bg-surface-2 text-white', mc.glow)
          : 'border-border bg-surface text-muted hover:bg-surface-2 hover:text-white',
      )}
    >
      <span aria-hidden>{icon}</span>
      <span className="text-micro text-vertical whitespace-nowrap">{label}</span>
      {badge && (
        <span className="text-micro rounded bg-surface px-1 py-0.5 text-muted">
          {badge}
        </span>
      )}
      {children}
    </button>
  );
}

interface PanelRailProps {
  open: PanelKey | undefined;
  onToggle: (panel: PanelKey) => void;
  /** Rendered as the read-only hover preview on the config tab. */
  summary: { agentName: string; provider: string; prompt: string };
  eventCount: number;
  /** Cancel is only reachable while a task is in flight. */
  running: boolean;
  onCancel: () => void;
  className?: string;
}

/**
 * The 56px rail the two step-2 side panels collapse into, so the agent canvas
 * gets their width back. Mirrors the task rail on the opposite edge.
 */
export function PanelRail({
  open,
  onToggle,
  summary,
  eventCount,
  running,
  onCancel,
  className,
}: PanelRailProps) {
  return (
    <div className={cn('flex w-14 shrink-0 flex-col gap-3', className)}>
      <RailTab
        label="Task config"
        icon={<SlidersHorizontal className="h-4 w-4" />}
        open={open === 'config'}
        onClick={() => onToggle('config')}
        controls="architect-config-panel"
      >
        <RailFlyout>
          <span className={cn('block', mc.text)}>{summary.agentName}</span>
          <span className="mt-1 block text-muted">{summary.provider}</span>
          <span className="mt-2 block font-mono normal-case text-slate-200">
            {preview(summary.prompt)}
          </span>
        </RailFlyout>
      </RailTab>

      {/* Sibling (not nested) button — cancels without opening the panel, the
          same reason the task rail keeps its delete button outside the row. */}
      {running && (
        <button
          type="button"
          onClick={onCancel}
          aria-label="Cancel task"
          title="Cancel task"
          className={cn(
            'flex shrink-0 items-center justify-center rounded-lg border py-3',
            'border-danger/40 bg-danger-dim text-danger transition-colors',
            'hover:border-danger hover:shadow-glow-danger',
            'focus:outline-none focus-visible:ring-2 focus-visible:ring-danger',
          )}
        >
          <Square className="h-3.5 w-3.5 fill-current" aria-hidden />
        </button>
      )}

      <RailTab
        label="Live log"
        icon={<Terminal className="h-4 w-4" />}
        open={open === 'log'}
        onClick={() => onToggle('log')}
        controls="architect-log-panel"
        badge={eventCount > 0 ? String(eventCount) : undefined}
      />
    </div>
  );
}
