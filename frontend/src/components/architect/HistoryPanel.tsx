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

interface HistoryPanelProps {
  items: TaskSummary[];
  loading: boolean;
  activeTaskId: string | undefined;
  onSelect: (taskId: string) => void;
}

/** Sidebar of the user's past tasks; selecting one reloads its full session. */
export function HistoryPanel({
  items,
  loading,
  activeTaskId,
  onSelect,
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
              <li key={task.task_id}>
                <button
                  type="button"
                  onClick={() => onSelect(task.task_id)}
                  aria-current={active ? 'true' : undefined}
                  className={cn(
                    'w-full border-l-2 px-4 py-3 text-left transition-colors hover:bg-surface-2',
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
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
