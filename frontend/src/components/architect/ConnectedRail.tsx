'use client';

// Connected-API rail for the architect canvas: one lane per BYOK service this
// squad can reach. A lane lights up and counts calls while subagents use it,
// and FlowLayer draws one line per subagent that actually went there — so "2 of
// 4 members hit X" is visible at a glance rather than buried in the log.
//
// Only credentialed tools appear here. web_search and data_fetch are always-on
// and keyless; giving them lanes would bury the signal this rail exists for.
//
// Lanes with no connected key render dim with a link to Settings > API Keys,
// which is the moment the missing integration is most worth surfacing.
//
// Rows register into the graph's shared node map so they can be edge endpoints;
// they must therefore live inside the FlowLayer container, not beside it.

import Link from 'next/link';
import { PROVIDER_MAP } from '@/lib/providers';
import { cn } from '@/lib/cn';

export interface ConnectedLane {
  /** Provider id — also the node key suffix and the event's `provider`. */
  provider: string;
  /** Completed calls to this provider in the current task. */
  calls: number;
  /** A call is in flight right now. */
  active: boolean;
  /** The user has a stored key (or the tool needs none, e.g. GitHub). */
  available: boolean;
  /** How many distinct team members reached for it. */
  members: number;
}

export function ConnectedRail({
  lanes,
  registerNode,
  rgb,
}: {
  lanes: ConnectedLane[];
  /** AgentGraph's callback-ref factory, so rows can anchor FlowLayer edges. */
  registerNode: (key: string) => (el: HTMLElement | null) => void;
  /** Space-separated RGB triplet for lit lanes (the routed domain hue). */
  rgb: string;
}) {
  if (lanes.length === 0) return null;

  return (
    <aside
      aria-label="Connected APIs"
      // Fixed width, never a transitioning one: FlowLayer re-measures on
      // container resize, and an animating width would drag the edges with it.
      className="relative hidden w-44 shrink-0 flex-col gap-2 lg:flex"
    >
      <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted">
        Connected
      </h3>
      <ul className="flex flex-col gap-1.5">
        {lanes.map((lane) => (
          <Lane
            key={lane.provider}
            lane={lane}
            registerNode={registerNode}
            rgb={rgb}
          />
        ))}
      </ul>
    </aside>
  );
}

function Lane({
  lane,
  registerNode,
  rgb,
}: {
  lane: ConnectedLane;
  registerNode: (key: string) => (el: HTMLElement | null) => void;
  rgb: string;
}) {
  const meta = PROVIDER_MAP[lane.provider as keyof typeof PROVIDER_MAP];
  const label = meta?.label ?? lane.provider;
  const used = lane.calls > 0 || lane.active;

  const row = (
    <div
      // The registered element is the row itself, so an edge lands on the lane
      // it describes rather than on the list.
      ref={registerNode(`api:${lane.provider}`)}
      className={cn(
        'flex items-center gap-2 rounded-sm border px-2 py-1.5 transition-colors',
        used
          ? 'border-transparent bg-surface'
          : 'border-dashed border-border/60 bg-transparent',
      )}
      style={used ? ({ '--bar-rgb': rgb } as React.CSSProperties) : undefined}
    >
      <span
        aria-hidden
        className={cn(
          'size-1.5 shrink-0 rounded-full',
          used ? 'rail-bar' : 'bg-muted/40',
          lane.active && 'animate-pulse-glow',
        )}
      />
      <span
        className={cn(
          'min-w-0 flex-1 truncate text-[11px]',
          used ? 'text-foreground' : 'text-muted',
        )}
      >
        {label}
      </span>
      {used ? (
        <span className="font-mono text-[10px] tabular-nums text-muted">
          {lane.calls}
        </span>
      ) : (
        <span className="text-[10px] text-muted">
          {lane.available ? '—' : 'connect'}
        </span>
      )}
    </div>
  );

  return (
    <li>
      {lane.available ? (
        row
      ) : (
        <Link
          href="/settings/api-keys"
          // The one moment this integration is obviously worth having is while
          // watching a task that could have used it.
          title={`Connect ${label} to let this squad use it`}
          className="block rounded-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-module-architect"
        >
          {row}
        </Link>
      )}
      {used && lane.members > 0 && (
        <p className="pl-6 pt-0.5 text-[10px] leading-tight text-muted">
          {lane.members} {lane.members === 1 ? 'member' : 'members'}
        </p>
      )}
    </li>
  );
}
