import { useLayoutEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import { cn } from '@/lib/cn';
import { formatTime, useTimeZone } from '@/lib/date';
import { describeSubagentActivity } from '@/lib/agent-locale';
import type { AgentEvent } from '@/types';

/** Distance from the bottom (px) within which the log still counts as "at bottom". */
const BOTTOM_THRESHOLD_PX = 24;

function describe(event: AgentEvent): string {
  switch (event.type) {
    case 'task_started':
      return 'Task started';
    case 'node_update': {
      const who = `${event.role ?? 'agent'}${
        event.index !== undefined ? ` #${event.index}` : ''
      }`;
      // A failed node names its cause; every other transition is just a state.
      const detail = event.error
        ? `: ${event.error}`
        : event.domain
          ? ` (domain: ${event.domain})`
          : '';
      return `${who} → ${event.state ?? ''}${detail}`;
    }
    case 'agent_warning':
      return event.message ?? 'Degraded';
    case 'agent_message':
      if (event.subtasks) return `Subtasks: ${event.subtasks.join(', ')}`;
      // Connected-API calls are named rather than collapsed to "Agent message",
      // so the log agrees with the rail on the canvas. The keyless tools keep
      // the old generic line — they have no lane and no provider.
      if (event.provider) {
        const label = describeSubagentActivity(event);
        return event.done ? `${label} — done` : label;
      }
      return 'Agent message';
    case 'review_result':
      return `Review: ${event.approved ? 'approved' : 'rejected'}`;
    case 'agent_question':
      return `Agent asked: ${event.question ?? ''}`;
    case 'user_answer':
      return `User answered: ${event.answer ?? ''}`;
    case 'task_completed':
      return 'Task completed';
    case 'task_completed_with_warnings':
      return 'Task completed with warnings';
    case 'task_cancelled':
      return 'Task cancelled';
    case 'task_failed':
      return `Task failed: ${event.error ?? ''}`;
    default:
      return event.type;
  }
}

function eventColor(event: AgentEvent): string {
  switch (event.type) {
    case 'task_completed':
      return 'text-primary';
    case 'task_completed_with_warnings':
    case 'task_cancelled':
      return 'text-warning';
    case 'task_failed':
      return 'text-danger';
    case 'agent_warning':
      return 'text-warning';
    case 'node_update':
      return event.state === 'error' ? 'text-danger' : 'text-accent';
    case 'agent_question':
      return 'text-accent';
    case 'review_result':
      return event.approved ? 'text-primary' : 'text-danger';
    default:
      return 'text-slate-200';
  }
}

/** Row highlight tint (rgb triplet) — feeds the decaying `log-flash`. */
function eventRgb(event: AgentEvent): string {
  switch (event.type) {
    case 'task_completed':
      return '211 203 192';
    case 'task_completed_with_warnings':
    case 'task_cancelled':
      return '255 122 69';
    case 'task_failed':
      return '255 77 109';
    case 'agent_warning':
      return '255 122 69';
    case 'review_result':
      return event.approved ? '211 203 192' : '255 77 109';
    case 'node_update':
      return event.state === 'error' ? '255 77 109' : '34 211 238';
    case 'agent_question':
      return '34 211 238';
    default:
      return '167 139 250';
  }
}

/** Terminal-style glyph per event type. */
function eventGlyph(event: AgentEvent): string {
  switch (event.type) {
    case 'task_completed':
      return '✓';
    case 'task_completed_with_warnings':
      return '⚠';
    case 'task_cancelled':
      return '⊘';
    case 'task_failed':
      return '✕';
    case 'agent_warning':
      return '⚠';
    case 'node_update':
      return event.state === 'error' ? '✕' : '›';
    case 'review_result':
      return event.approved ? '✓' : '✕';
    case 'agent_question':
      return '?';
    default:
      return '›';
  }
}

interface EventLogProps {
  events: AgentEvent[];
  /**
   * Leading rows delivered in bulk (snapshot replay) render without the
   * entrance flash, so a reconnect never cascades hundreds of animations.
   */
  staticCount?: number;
}

export function EventLog({ events, staticCount = 0 }: EventLogProps) {
  const tz = useTimeZone();
  const containerRef = useRef<HTMLDivElement>(null);
  // Follow new events only while the user is already at the bottom of the log.
  const stickToBottomRef = useRef(true);

  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    stickToBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD_PX;
  };

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (el && stickToBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [events.length]);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="scrollbar-thin h-full overflow-y-auto rounded-md border border-border bg-background/80 p-3 font-mono text-xs"
    >
      {events.length === 0 ? (
        <p className="text-muted">&gt; No events yet. Start a task.</p>
      ) : (
        events.map((event, i) => {
          // Synthesis streaming deltas are merged into the answer panel, not the
          // log — rendering each one raw would flood the terminal with noise.
          if (event.type === 'agent_delta') return null;
          const live = i >= staticCount;
          return (
            <div
              key={i}
              className={cn('flex gap-2 rounded-sm px-1 py-0.5', live && 'log-flash')}
              style={
                live ? ({ ['--lg-rgb' as string]: eventRgb(event) } as CSSProperties) : undefined
              }
            >
              <span className={cn('shrink-0', eventColor(event))} aria-hidden>
                {eventGlyph(event)}
              </span>
              <span className="shrink-0 text-muted/60">
                {event.ts ? formatTime(event.ts, tz) : ''}
              </span>
              <span className={cn(eventColor(event))}>{describe(event)}</span>
            </div>
          );
        })
      )}
      <p className="py-0.5 text-module-architect">
        &gt;<span className="animate-blink">_</span>
      </p>
    </div>
  );
}
