'use client';

// Living connector layer for the architect graph: cubic Bézier edges drawn in
// an absolutely-positioned SVG behind the DOM nodes, with glowing energy
// pulses travelling along active edges. One shared rAF loop drives every
// pulse and runs only while at least one edge is active. Node positions are
// read from offsetLeft/offsetTop (layout coords), so entrance transforms on
// the nodes never skew the wiring.

import { useCallback, useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { useReducedMotion } from '@/lib/motion';

export interface FlowEdge {
  from: string;
  to: string;
  active: boolean;
  done: boolean;
  /**
   * Anchor geometry. 'vertical' (the default) leaves the bottom of `from` and
   * enters the top of `to` — the top-down agent hierarchy. 'horizontal' leaves
   * the right edge and enters the left, for the connected-API rail beside the
   * graph. Defaulting keeps every existing call site unchanged.
   */
  orientation?: 'vertical' | 'horizontal';
  /** Per-edge RGB triplet; falls back to the layer-wide `rgb` prop. */
  rgb?: string;
}

interface FlowLayerProps {
  edges: FlowEdge[];
  /** Node key → element registry, populated by AgentGraph's callback refs. */
  nodesRef: RefObject<Map<string, HTMLElement>>;
  /** The `relative` graph container the SVG overlays. */
  containerRef: RefObject<HTMLElement | null>;
  /** Space-separated RGB triplet for active/done edges and pulses. */
  rgb: string;
}

const PULSES_PER_EDGE = 2;
const PULSE_CYCLE_MS = 1400;

interface EdgePath {
  key: string;
  d: string;
  active: boolean;
  done: boolean;
  rgb?: string;
}

/** Layout-coordinate offset of `el` within `container` (transform-immune). */
function offsetWithin(
  el: HTMLElement,
  container: HTMLElement,
): { x: number; y: number } {
  let x = 0;
  let y = 0;
  let node: HTMLElement | null = el;
  while (node && node !== container) {
    x += node.offsetLeft;
    y += node.offsetTop;
    node = node.offsetParent as HTMLElement | null;
  }
  return { x, y };
}

export function FlowLayer({
  edges,
  nodesRef,
  containerRef,
  rgb,
}: FlowLayerProps) {
  const reduced = useReducedMotion();
  const [paths, setPaths] = useState<EdgePath[]>([]);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const pathEls = useRef<Map<string, SVGPathElement>>(new Map());
  const pulseEls = useRef<Map<string, SVGCircleElement>>(new Map());

  // Signature of the edge topology + states — drives re-measure and the loop.
  const signature = edges
    .map(
      (e) =>
        `${e.from}>${e.to}:${e.active ? 1 : e.done ? 2 : 0}:${e.orientation ?? 'v'}`,
    )
    .join('|');

  const measure = useCallback(() => {
    const container = containerRef.current;
    const nodes = nodesRef.current;
    if (!container || !nodes) return;
    setSize({ w: container.offsetWidth, h: container.offsetHeight });
    const next: EdgePath[] = [];
    for (const edge of edges) {
      const fromEl = nodes.get(edge.from);
      const toEl = nodes.get(edge.to);
      if (!fromEl || !toEl) continue;
      const fo = offsetWithin(fromEl, container);
      const to = offsetWithin(toEl, container);
      let d: string;
      if (edge.orientation === 'horizontal') {
        // Right edge of `from` into the left edge of `to`, bending on X so the
        // curve reads as a branch off the hierarchy rather than part of it.
        const x1 = fo.x + fromEl.offsetWidth;
        const y1 = fo.y + fromEl.offsetHeight / 2;
        const x2 = to.x;
        const y2 = to.y + toEl.offsetHeight / 2;
        const bend = Math.max((x2 - x1) * 0.5, 18);
        d = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
      } else {
        const x1 = fo.x + fromEl.offsetWidth / 2;
        const y1 = fo.y + fromEl.offsetHeight;
        const x2 = to.x + toEl.offsetWidth / 2;
        const y2 = to.y;
        const bend = Math.max((y2 - y1) * 0.6, 14);
        d = `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
      }
      next.push({
        key: `${edge.from}>${edge.to}`,
        d,
        active: edge.active,
        done: edge.done,
        rgb: edge.rgb,
      });
    }
    setPaths(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, containerRef, nodesRef]);

  useEffect(() => {
    measure();
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    // Also observe every node element, not just the container. The subagent
    // grid cells change width whenever the flex graph column reflows — e.g. the
    // connected-API rail loads in after a tab switch and squeezes the column —
    // while the container's own size stays fixed. A container-only observer
    // misses that reflow, leaving the main→subagent edges pinned to the nodes'
    // former (further-right) positions until an unrelated resize forces a
    // re-measure. Observing the cells themselves catches the shift directly.
    const nodes = nodesRef.current;
    if (nodes) for (const el of nodes.values()) observer.observe(el);
    return () => observer.disconnect();
  }, [measure, containerRef, nodesRef]);

  // Single shared rAF loop — advances every pulse along its path. Runs only
  // while at least one edge is active; rAF is suspended by the browser when
  // the tab is hidden, so no explicit visibility handling is needed.
  const anyActive = !reduced && paths.some((p) => p.active);
  useEffect(() => {
    if (!anyActive) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = (now - t0) / PULSE_CYCLE_MS;
      for (const [id, circle] of pulseEls.current) {
        const sep = id.lastIndexOf('#');
        const path = pathEls.current.get(id.slice(0, sep));
        if (!path) continue;
        const phase = Number(id.slice(sep + 1)) / PULSES_PER_EDGE;
        const len = path.getTotalLength();
        if (len === 0) continue;
        const point = path.getPointAtLength(((t + phase) % 1) * len);
        circle.setAttribute('cx', point.x.toFixed(1));
        circle.setAttribute('cy', point.y.toFixed(1));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [anyActive, paths]);

  if (paths.length === 0 || size.w === 0) return null;

  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0"
      width={size.w}
      height={size.h}
      viewBox={`0 0 ${size.w} ${size.h}`}
      fill="none"
    >
      <defs>
        <filter id="flow-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {paths.map((p) => (
        <path
          key={p.key}
          ref={(el) => {
            if (el) pathEls.current.set(p.key, el);
            else pathEls.current.delete(p.key);
          }}
          d={p.d}
          strokeWidth={p.active ? 1.5 : 1}
          strokeLinecap="round"
          className={p.active && !reduced ? 'animate-flow-dash' : undefined}
          stroke={p.active || p.done ? `rgb(${p.rgb ?? rgb})` : '#3d3d5c'}
          strokeOpacity={p.active ? 0.9 : p.done ? 0.45 : 0.5}
          strokeDasharray={
            p.active && !reduced ? '6 6' : p.done ? undefined : '4 4'
          }
          filter={p.active ? 'url(#flow-glow)' : undefined}
        />
      ))}
      {!reduced &&
        paths
          .filter((p) => p.active)
          .flatMap((p) =>
            Array.from({ length: PULSES_PER_EDGE }, (_, i) => (
              <circle
                key={`${p.key}#${i}`}
                ref={(el) => {
                  if (el) pulseEls.current.set(`${p.key}#${i}`, el);
                  else pulseEls.current.delete(`${p.key}#${i}`);
                }}
                r={2.5}
                fill={`rgb(${p.rgb ?? rgb})`}
                filter="url(#flow-glow)"
              />
            )),
          )}
    </svg>
  );
}
