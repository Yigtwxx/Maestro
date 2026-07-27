// Pure, dependency-free helpers for the trace waterfall. All layout math and
// attribute plumbing lives here so the components stay presentational and this
// logic stays unit-testable.

import { domainColor } from '@/lib/agent-colors';
import type { SpanKind, SpanStatus, TraceSpan } from '@/types';

/** A span with its resolved children and tree depth (root = 0). */
export interface TraceNode {
  span: TraceSpan;
  children: TraceNode[];
  depth: number;
}

/** The absolute time window a trace spans, in epoch milliseconds. */
export interface TraceWindow {
  t0: number;
  t1: number;
  /** Always >= 1 so callers can divide without guarding against zero. */
  totalMs: number;
}

/** A span bar's position on the timeline track, as track-width percentages. */
export interface SpanGeometry {
  leftPct: number;
  widthPct: number;
}

// The danger semantic (tailwind `danger`) — error spans always read red,
// regardless of kind or domain.
const ERROR_HEX = '#ff4d6d';

// Stable per-kind fallback hues (dark chart band), used when a span carries no
// `maestro.domain`. Distinct enough to double as a legend.
const SPAN_KIND_HEX: Record<SpanKind, string> = {
  task: '#6d7cff', // indigo — the root container
  step: '#1594ae', // teal — routing / execution phases
  agent: '#2f86e6', // blue — a team member
  llm: '#12a074', // green — the billable model call
  tool: '#c17d08', // gold — an external tool invocation
};

/**
 * Build the span forest from a flat, start-time-sorted span list. Links each
 * span to its parent via `parent_span_id`; a span whose parent id is absent
 * (possible under the 1000-span server cap) is promoted to a root so nothing is
 * dropped. Sibling order follows input order (already start_time ASC).
 */
export function buildTraceTree(spans: TraceSpan[]): TraceNode[] {
  const nodes = new Map<string, TraceNode>();
  for (const span of spans) {
    nodes.set(span.span_id, { span, children: [], depth: 0 });
  }

  const roots: TraceNode[] = [];
  for (const span of spans) {
    const node = nodes.get(span.span_id);
    if (!node) continue;
    const parent =
      span.parent_span_id !== null ? nodes.get(span.parent_span_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  // Assign depth top-down so children of promoted orphans still nest correctly.
  const assignDepth = (node: TraceNode, depth: number): void => {
    node.depth = depth;
    for (const child of node.children) assignDepth(child, depth + 1);
  };
  for (const root of roots) assignDepth(root, 0);

  return roots;
}

/** DFS pre-order flatten — the row order the waterfall renders top to bottom. */
export function flattenTree(roots: TraceNode[]): TraceNode[] {
  const rows: TraceNode[] = [];
  const walk = (node: TraceNode): void => {
    rows.push(node);
    for (const child of node.children) walk(child);
  };
  for (const root of roots) walk(root);
  return rows;
}

/** Min start / max end across all spans. Empty input yields a 1ms window. */
export function traceWindow(spans: TraceSpan[]): TraceWindow {
  let t0 = Number.POSITIVE_INFINITY;
  let t1 = Number.NEGATIVE_INFINITY;
  for (const span of spans) {
    const start = Date.parse(span.start_time);
    const end = Date.parse(span.end_time);
    if (!Number.isNaN(start)) t0 = Math.min(t0, start);
    if (!Number.isNaN(end)) t1 = Math.max(t1, end);
  }
  if (!Number.isFinite(t0) || !Number.isFinite(t1)) {
    return { t0: 0, t1: 0, totalMs: 1 };
  }
  return { t0, t1, totalMs: Math.max(t1 - t0, 1) };
}

/**
 * A span's bar geometry as percentages of the timeline track. Sub-millisecond
 * spans get a real (if tiny) width; components enforce a minimum *pixel* width
 * so the bar stays visible without distorting the percentage alignment.
 */
export function spanGeometry(
  span: TraceSpan,
  window: TraceWindow,
): SpanGeometry {
  const start = Date.parse(span.start_time);
  const offset = Number.isNaN(start) ? 0 : start - window.t0;
  const leftPct = clampPct((offset / window.totalMs) * 100);
  const widthPct = clampPct(
    (Math.max(span.duration_ms, 0) / window.totalMs) * 100,
    100 - leftPct,
  );
  return { leftPct, widthPct };
}

function clampPct(value: number, max = 100): number {
  if (Number.isNaN(value)) return 0;
  return Math.min(Math.max(value, 0), max);
}

// --- Attribute accessors (keep the dotted bag out of the components) ---

/** The served model if known, else the requested one. */
export function spanModel(span: TraceSpan): string | undefined {
  return (
    span.attributes['gen_ai.response.model'] ??
    span.attributes['gen_ai.request.model']
  );
}

export function spanTokens(span: TraceSpan): { input: number; output: number } {
  return {
    input: span.attributes['gen_ai.usage.input_tokens'] ?? 0,
    output: span.attributes['gen_ai.usage.output_tokens'] ?? 0,
  };
}

/** True when the token counts were estimated (provider returned no usage). */
export function spanIsEstimated(span: TraceSpan): boolean {
  return span.attributes['maestro.tokens.estimated'] === true;
}

/** The provider that actually served the call, if recorded. */
export function spanProvider(span: TraceSpan): string | undefined {
  return span.attributes['gen_ai.system'] ?? span.attributes['maestro.provider'];
}

export function spanDomain(span: TraceSpan): string | undefined {
  return span.attributes['maestro.domain'];
}

export function spanFinishReason(span: TraceSpan): string | undefined {
  return span.attributes['gen_ai.response.finish_reason'];
}

/** True for the billable model-call spans (the only ones with nonzero cost). */
export function isLlmSpan(span: TraceSpan): boolean {
  return span.kind === 'llm';
}

/**
 * The bar hue for a span: danger on error, else the domain hue when the span
 * carries one (agents, execute step), else a stable per-kind fallback.
 */
export function spanColorHex(span: TraceSpan): string {
  if (span.status === 'error') return ERROR_HEX;
  const domain = spanDomain(span);
  if (domain) return domainColor(domain).chartHex;
  return SPAN_KIND_HEX[span.kind] ?? SPAN_KIND_HEX.step;
}

/** The fallback hue for a kind, independent of any span — for legends. */
export function kindColorHex(kind: SpanKind): string {
  return SPAN_KIND_HEX[kind] ?? SPAN_KIND_HEX.step;
}

// --- Display formatting ---

// Plain-language names for the span taxonomy, so the UI never shows a raw enum
// (`llm`, `tool`, …) the user has to decode.
const SPAN_KIND_LABEL: Record<SpanKind, string> = {
  task: 'Full task',
  step: 'Phase',
  agent: 'Agent',
  llm: 'Model call',
  tool: 'Tool call',
};

const SPAN_STATUS_LABEL: Record<SpanStatus, string> = {
  ok: 'Succeeded',
  error: 'Failed',
};

/** Friendly name for a span kind; falls back to the raw value if unknown. */
export function spanKindLabel(kind: SpanKind): string {
  return SPAN_KIND_LABEL[kind] ?? kind;
}

/** Friendly name for a span status; falls back to the raw value if unknown. */
export function spanStatusLabel(status: SpanStatus): string {
  return SPAN_STATUS_LABEL[status] ?? status;
}

/** ISO -> readable local timestamp; falls back to the raw string if unparseable. */
export function formatTimestamp(iso: string): string {
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return iso;
  return new Date(ms).toLocaleString();
}

/** Human-readable duration: sub-second in ms, else seconds to 2 dp. */
export function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

/** Cost with enough precision to show fractions of a cent; '$0' when zero. */
export function formatUsd(cost: number, dp = 6): string {
  if (cost === 0) return '$0';
  return `$${cost.toFixed(dp)}`;
}

/** Compact integer with thousands separators (locale-independent grouping). */
export function formatCount(n: number): string {
  return n.toLocaleString('en-US');
}
