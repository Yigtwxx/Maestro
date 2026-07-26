'use client';

import type { CSSProperties } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { isLiveStatus, statusRgb } from '@/components/ui/Badge';
import { cn } from '@/lib/cn';
import { relativeTime } from '@/lib/date';
import { MODULE_COLOR } from '@/lib/module-colors';
import { SPRING, useReducedMotion } from '@/lib/motion';
import type { TaskSummary } from '@/types';

/** Characters of the prompt shown in the hover label before it is cut. */
const PREVIEW_LEN = 60;

/** Hue of the "new task" bar capping the rail. */
const NEW_TASK_RGB = '255 255 255';

/** Neutral hue for the loading placeholder bars — `border-bright`. */
const IDLE_RGB = '61 61 92';

function preview(prompt: string): string {
  return prompt.length > PREVIEW_LEN
    ? `${prompt.slice(0, PREVIEW_LEN).trimEnd()}…`
    : prompt;
}

interface RailLabelProps {
  children: React.ReactNode;
}

/**
 * Hover/focus caption that flies out to the right of a bar. There is no Tooltip
 * primitive in the project, and this needs no positioning logic — but it does
 * require every ancestor to stay overflow-visible, which is why the rail never
 * scrolls internally.
 */
function RailLabel({ children }: RailLabelProps) {
  return (
    <span
      className={cn(
        // Anchored to the leader's elbow (y = +11px from the row centre) rather
        // than to the bar, so the line points into it instead of running past.
        'pointer-events-none absolute left-full top-1/2 z-20 ml-7 mt-[11px] hidden -translate-y-1/2',
        'whitespace-nowrap rounded',
        'border border-border bg-surface-2 px-2 py-1 text-left text-micro text-slate-200',
        'group-hover:block group-focus-visible:block',
      )}
    >
      {children}
    </span>
  );
}

/**
 * Annotation leader drawn from a hovered bar into its flyout label. Two
 * segments — a 45° diagonal, then a short horizontal run — so the label reads
 * as called out rather than merely adjacent. It starts 6px *inside* the bar and
 * paints beneath it (the bar carries `z-10`), so the line emerges exactly at
 * the bar's edge whatever the hover state does to that edge: thickened,
 * rotated 4° down, or left flat under `prefers-reduced-motion`. Anchoring it to
 * the bar's resting corner instead left a visible gap once the bar rotated.
 * Inherits the bar's status hue via `--bar-rgb`.
 */
function RailLeader() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 35 12"
      width={35}
      height={12}
      fill="none"
      className={cn(
        'pointer-events-none absolute left-full top-1/2 -ml-1.5 hidden',
        'group-hover:block group-focus-visible:block',
      )}
    >
      <path
        d="M0.5 1 L10.5 11 L34.5 11"
        stroke="rgb(var(--bar-rgb, 139 143 163))"
        strokeWidth={1}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

interface TaskRailProps {
  items: TaskSummary[];
  loading: boolean;
  activeTaskId: string | undefined;
  /** Opens the task's detail dialog. */
  onSelect: (taskId: string) => void;
  onNewTask: () => void;
}

/**
 * The task history as a stack of thin status bars — a spectrum analyser rather
 * than a list, newest at the top, capped by a white "new task" bar. Each bar
 * carries its task's status hue; the one open in the canvas thickens and blooms
 * in the module color. Detail lives behind a click, so the rail costs ~56px of
 * width and one 24px row per task.
 */
export function TaskRail({
  items,
  loading,
  activeTaskId,
  onSelect,
  onNewTask,
}: TaskRailProps) {
  const reduced = useReducedMotion();

  return (
    // The rail lifts as a whole: motion leaves a transform/filter on every row,
    // so each one is its own stacking context and the hover label's z-index
    // cannot escape it. Sits above the agent graph (max z-30) and below the
    // modal and toaster (z-50).
    <nav aria-label="Task history" className="relative z-40 flex flex-col">
      <h2 className="sr-only">Task history</h2>

      {/* Cap of the stack — starts a fresh task. Kept full-width so it lines up
          with the history bars; the white hue is what sets it apart. */}
      <button
        type="button"
        onClick={onNewTask}
        title="New task"
        aria-label="New task"
        style={{ ['--bar-rgb' as string]: NEW_TASK_RGB } as CSSProperties}
        className="group relative mb-3 flex h-6 w-full items-center focus:outline-none"
      >
        <span
          className={cn(
            // `relative z-10` keeps the bar above the leader, which starts
            // underneath it so the two never separate.
            'rail-bar relative z-10 h-2.5 w-full origin-left rounded-full transition-transform',
            'motion-reduce:transition-none',
            'motion-safe:group-hover:scale-x-105 group-focus-visible:scale-x-105',
            'motion-safe:group-hover:rotate-[4deg] group-focus-visible:rotate-[4deg]',
          )}
        />
        <RailLeader />
        <RailLabel>New task</RailLabel>
      </button>

      {loading && items.length === 0 ? (
        <div className="flex flex-col" aria-hidden>
          {[0, 1, 2].map((i) => (
            <span key={i} className="flex h-6 w-full items-center">
              <span
                style={{ ['--bar-rgb' as string]: IDLE_RGB } as CSSProperties}
                className="rail-bar h-1.5 w-full animate-pulse rounded-full"
              />
            </span>
          ))}
        </div>
      ) : (
        <ul className="flex flex-col">
          <AnimatePresence initial={false}>
            {items.map((task) => {
              const active = task.task_id === activeTaskId;
              const rgb = statusRgb(task.status);
              return (
                <motion.li
                  key={task.task_id}
                  layout={!reduced}
                  // A bar slides in from above and flares once as it lands —
                  // the arrival cue. `initial={false}` on AnimatePresence keeps
                  // the whole stack from playing this on first paint.
                  initial={{ opacity: 0, y: -6, scaleY: 0.4, filter: 'brightness(1.8)' }}
                  animate={{ opacity: 1, y: 0, scaleY: 1, filter: 'brightness(1)' }}
                  exit={{ opacity: 0, scaleY: 0.4 }}
                  transition={reduced ? { duration: 0 } : SPRING.pop}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(task.task_id)}
                    aria-current={active ? 'true' : undefined}
                    aria-label={`${task.status} — ${preview(task.prompt)}`}
                    style={
                      {
                        ['--bar-rgb' as string]: rgb,
                        ...(active
                          ? { ['--glow-rgb' as string]: MODULE_COLOR.architect.rgb }
                          : {}),
                      } as CSSProperties
                    }
                    className="group relative flex h-6 w-full items-center focus:outline-none"
                  >
                    <span
                      className={cn(
                        // `relative z-10` — see RailLeader: the leader starts
                        // beneath the bar so it stays attached to its edge.
                        'rail-bar relative z-10 w-full origin-left rounded-full transition-all duration-150',
                        'motion-reduce:transition-none',
                        active ? 'h-2.5 rail-bar-active' : 'h-1.5',
                        isLiveStatus(task.status) && 'animate-pulse-glow',
                        'motion-safe:group-hover:h-2.5 group-focus-visible:h-2.5',
                        'motion-safe:group-hover:rotate-[4deg] group-focus-visible:rotate-[4deg]',
                      )}
                    />
                    <RailLeader />
                    <RailLabel>
                      <span className="block text-muted">
                        {relativeTime(task.created_at)}
                      </span>
                      <span className="block font-mono normal-case">
                        {preview(task.prompt)}
                      </span>
                    </RailLabel>
                  </button>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
    </nav>
  );
}
