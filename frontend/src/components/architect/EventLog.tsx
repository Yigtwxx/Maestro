import { useLayoutEffect, useRef } from 'react';
import type { CSSProperties } from 'react';
import { cn } from '@/lib/cn';
import type { AgentEvent } from '@/types';

/** Distance from the bottom (px) within which the log still counts as "at bottom". */
const BOTTOM_THRESHOLD_PX = 24;

function describe(event: AgentEvent): string {
  switch (event.type) {
    case 'task_started':
      return 'Task started';
    case 'node_update':
      return `${event.role ?? 'agent'}${
        event.index !== undefined ? ` #${event.index}` : ''
      } → ${event.state ?? ''}${event.domain ? ` (domain: ${event.domain})` : ''}`;
    case 'agent_message':
      return event.subtasks
        ? `Subtasks: ${event.subtasks.join(', ')}`
        : 'Agent message';
    case 'review_result':
      return `Review: ${event.approved ? 'approved' : 'rejected'}`;
    case 'agent_question':
      return `Agent asked: ${event.question ?? ''}`;
    case 'user_answer':
      return `User answered: ${event.answer ?? ''}`;
    case 'task_completed':
      return 'Task completed';
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
    case 'task_failed':
      return 'text-danger';
    case 'node_update':
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
      return '163 230 53';
    case 'task_failed':
      return '255 77 109';
    case 'review_result':
      return event.approved ? '163 230 53' : '255 77 109';
    case 'node_update':
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
    case 'task_failed':
      return '✕';
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
                {event.ts ? new Date(event.ts).toLocaleTimeString() : ''}
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
