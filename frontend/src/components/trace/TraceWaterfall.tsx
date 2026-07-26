'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/cn';
import type { SpanKind, TraceSpan } from '@/types';
import {
  buildTraceTree,
  flattenTree,
  formatDurationMs,
  formatUsd,
  isLlmSpan,
  kindColorHex,
  spanColorHex,
  spanGeometry,
  traceWindow,
  type TraceNode,
} from '@/lib/trace';

// Server-side cap (constants.TRACE_SPANS_MAX). At the ceiling the trace may be
// truncated, so we flag it rather than implying completeness.
const SPAN_CAP = 1000;

const LEGEND_KINDS: SpanKind[] = ['task', 'step', 'agent', 'llm', 'tool'];

interface TraceWaterfallProps {
  spans: TraceSpan[];
  selectedSpanId?: string;
  onSelectSpan?: (spanId: string) => void;
}

/**
 * Time-scaled span waterfall (Gantt). Bar position/width are pure functions of
 * the trace window (percentages via `spanGeometry`); tree depth drives the
 * gutter indent. No DOM measurement — layout is data, not geometry read back.
 */
export function TraceWaterfall({ spans, selectedSpanId, onSelectSpan }: TraceWaterfallProps) {
  const { rows, window, ticks } = useMemo(() => {
    const tree = buildTraceTree(spans);
    const flat = flattenTree(tree);
    const win = traceWindow(spans);
    // Five evenly spaced axis ticks across the window.
    const tickList = Array.from({ length: 5 }, (_, i) => ({
      pct: i * 25,
      label: formatDurationMs((win.totalMs * i) / 4),
    }));
    return { rows: flat, window: win, ticks: tickList };
  }, [spans]);

  return (
    <div className="rounded-lg border border-border bg-surface">
      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-border px-4 py-2.5">
        {LEGEND_KINDS.map((kind) => (
          <span key={kind} className="flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: kindColorHex(kind) }}
              aria-hidden
            />
            <span className="text-micro text-muted">{kind}</span>
          </span>
        ))}
        <span className="ml-auto font-mono text-micro text-muted">
          {rows.length} spans · {formatDurationMs(window.totalMs)}
        </span>
      </div>

      {/* Axis header */}
      <div className="flex items-center border-b border-border px-4 py-1.5">
        <div className="w-2/5 shrink-0 pr-3">
          <span className="text-micro text-muted">SPAN</span>
        </div>
        <div className="relative h-4 flex-1">
          {ticks.map((t, i) => (
            <span
              key={t.pct}
              className={cn(
                'absolute font-mono text-micro text-muted',
                i === 0 && 'left-0',
                i === ticks.length - 1 && 'right-0',
              )}
              style={i === 0 || i === ticks.length - 1 ? undefined : { left: `${t.pct}%` }}
            >
              {t.label}
            </span>
          ))}
        </div>
      </div>

      {/* Rows */}
      <div className="max-h-[32rem] overflow-y-auto">
        {rows.map((node) => (
          <WaterfallRow
            key={node.span.span_id}
            node={node}
            window={window}
            selected={node.span.span_id === selectedSpanId}
            onSelect={onSelectSpan}
          />
        ))}
      </div>

      {spans.length >= SPAN_CAP && (
        <p className="border-t border-border px-4 py-2 text-micro text-muted">
          Showing the first {SPAN_CAP} spans; this trace may be truncated.
        </p>
      )}
    </div>
  );
}

function WaterfallRow({
  node,
  window,
  selected,
  onSelect,
}: {
  node: TraceNode;
  window: ReturnType<typeof traceWindow>;
  selected: boolean;
  onSelect?: (spanId: string) => void;
}) {
  const { span, depth } = node;
  const { leftPct, widthPct } = spanGeometry(span, window);
  const hex = spanColorHex(span);
  const isError = span.status === 'error';
  const clickable = onSelect !== undefined;

  return (
    <div
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => onSelect(span.span_id) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelect(span.span_id);
              }
            }
          : undefined
      }
      className={cn(
        'flex items-center border-b border-border/50 px-4 py-1.5 transition-colors',
        clickable && 'cursor-pointer hover:bg-surface-2',
        selected && 'bg-surface-2',
      )}
    >
      {/* Gutter: indented name + duration */}
      <div
        className="flex w-2/5 shrink-0 items-center gap-2 pr-3"
        style={{ paddingLeft: `${depth * 14}px` }}
      >
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: hex }}
          aria-hidden
        />
        <span
          className={cn('truncate font-mono text-xs', isError ? 'text-danger' : 'text-slate-200')}
          title={span.name}
        >
          {span.name}
        </span>
        <span className="ml-auto shrink-0 font-mono text-micro text-muted">
          {formatDurationMs(span.duration_ms)}
        </span>
      </div>

      {/* Track: the positioned bar */}
      <div className="relative h-4 flex-1">
        <div
          className={cn(
            'absolute top-1/2 flex h-3 -translate-y-1/2 items-center overflow-hidden rounded-sm px-1',
            selected && 'ring-1 ring-white/50',
          )}
          style={{
            left: `${leftPct}%`,
            width: `${widthPct}%`,
            minWidth: '3px',
            backgroundColor: hex,
          }}
          title={`${span.name} · ${formatDurationMs(span.duration_ms)}`}
        >
          {isLlmSpan(span) && span.cost_usd > 0 && (
            <span className="whitespace-nowrap text-[9px] font-medium leading-none text-black/80">
              {formatUsd(span.cost_usd, 4)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
