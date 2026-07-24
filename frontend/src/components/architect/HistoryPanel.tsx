'use client';

import { Badge } from '@/components/ui/Badge';
import { SkeletonList } from '@/components/ui/Skeleton';
import { cn } from '@/lib/cn';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { TaskSummary } from '@/types';

const mc = MODULE_COLOR.architect;

const relativeTime = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

// Ordered smallest-to-largest; each `amount` is how many of that unit fit in
// the next one up.
const DIVISIONS = [
  { amount: 60, unit: 'second' },
  { amount: 60, unit: 'minute' },
  { amount: 24, unit: 'hour' },
  { amount: 7, unit: 'day' },
  { amount: 4.34524, unit: 'week' },
  { amount: 12, unit: 'month' },
  { amount: Number.POSITIVE_INFINITY, unit: 'year' },
] as const;

function timeAgo(isoTimestamp: string): string {
  let delta = (new Date(isoTimestamp).getTime() - Date.now()) / 1000;
  for (const division of DIVISIONS) {
    if (Math.abs(delta) < division.amount) {
      return relativeTime.format(Math.round(delta), division.unit);
    }
    delta /= division.amount;
  }
  return '';
}

/** Outline trash glyph for the per-task delete control. */
function TrashIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
    </svg>
  );
}

interface HistoryPanelProps {
  items: TaskSummary[];
  loading: boolean;
  activeTaskId: string | undefined;
  onSelect: (taskId: string) => void;
  onDelete: (taskId: string) => void;
}

/** Sidebar of the user's past tasks; selecting one reloads its full session. */
export function HistoryPanel({
  items,
  loading,
  activeTaskId,
  onSelect,
  onDelete,
}: HistoryPanelProps) {
  return (
    <aside className="h-fit rounded-lg border border-border bg-surface">
      <div className={`text-micro border-b border-border px-4 py-3 ${mc.text}`}>
        [ TASK HISTORY ]
      </div>

      {loading && items.length === 0 ? (
        <div className="px-4 py-5">
          <SkeletonList module="architect" rows={3} />
        </div>
      ) : items.length === 0 ? (
        <p className="px-4 py-5 text-sm text-muted">&gt; No tasks yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {items.map((task) => {
            const active = task.task_id === activeTaskId;
            return (
              <li key={task.task_id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(task.task_id)}
                  aria-current={active ? 'true' : undefined}
                  className={cn(
                    'w-full border-l-2 py-3 pl-4 pr-9 text-left transition-colors hover:bg-surface-2',
                    active
                      ? 'border-l-module-architect bg-surface-2'
                      : 'border-l-transparent',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge status={task.status} />
                    <span className="text-micro shrink-0 text-muted">
                      {timeAgo(task.created_at)}
                    </span>
                  </div>
                  <p className="mt-2 line-clamp-2 font-mono text-sm text-slate-200">
                    {task.prompt}
                  </p>
                </button>
                {/* Sibling (not nested) button — deletes without opening the task. */}
                <button
                  type="button"
                  onClick={() => onDelete(task.task_id)}
                  aria-label="Delete task"
                  title="Delete task"
                  className={cn(
                    'absolute right-2 top-2 rounded p-1 text-muted transition-colors',
                    'hover:bg-danger/10 hover:text-danger',
                    // Hover-capable pointers reveal it on row hover/focus; touch
                    // devices (no hover) keep it visible so it stays reachable.
                    '[@media(hover:hover)]:opacity-0',
                    'group-hover:opacity-100 focus-visible:opacity-100',
                  )}
                >
                  <TrashIcon />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
