'use client';

import { useRef } from 'react';
import { motion } from 'motion/react';
import { Bot, Cpu, ShieldCheck, Workflow } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/cn';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { domainColor } from '@/lib/agent-colors';
import { MODULE_COLOR } from '@/lib/module-colors';
import { SPRING, useReducedMotion } from '@/lib/motion';
import { FlowLayer, type FlowEdge } from '@/components/architect/FlowLayer';

export type NodeState = 'idle' | 'running' | 'done' | 'error';

export interface NodeDetails {
  /** Full brief/message the main agent sent to this subagent. */
  brief: string;
  /** Latest tool activity one-liner, if the subagent has emitted any. */
  activity?: string;
  /** Display names of assignments this one depends on. */
  dependsOn?: string[];
}

export interface GraphNode {
  key: string;
  label: string;
  sublabel?: string;
  state: NodeState;
  /** When set, the node reveals an expanded detail overlay on hover/focus. */
  details?: NodeDetails;
}

const stateRing: Record<NodeState, string> = {
  idle: 'border-border text-muted',
  running: 'border-accent/70 text-white shadow-glow-cyan',
  done: 'border-module-architect/60 text-white',
  error: 'border-danger/60 text-white shadow-glow-danger',
};

const stateLabel: Record<NodeState, string> = {
  idle: '[ IDLE ]',
  running: '[ RUNNING ]',
  done: '[ DONE ]',
  error: '[ ERROR ]',
};

const stateLabelColor: Record<NodeState, string> = {
  idle: 'text-muted',
  running: 'text-accent',
  done: 'text-module-architect',
  error: 'text-danger',
};

// One-shot / looping state effects layered onto the base card.
const stateEffect: Record<NodeState, string | undefined> = {
  idle: undefined,
  running: undefined, // the ping ring below carries the "alive" signal
  done: 'animate-pop-flash motion-reduce:animate-none',
  error: 'animate-shake motion-reduce:animate-none',
};

function nodeIcon(key: string): LucideIcon {
  if (key === 'orchestrator') return Workflow;
  if (key === 'reviewer') return ShieldCheck;
  if (key.startsWith('sub')) return Cpu;
  return Bot;
}

/**
 * Expanded detail card revealed over a node on hover/focus. Absolutely
 * positioned so it never changes the layout metrics FlowLayer measures
 * edge endpoints from — the SVG connectors stay put while it is open.
 */
function NodeDetailOverlay({ node, domain }: { node: GraphNode; domain?: string }) {
  const details = node.details;
  if (!details) return null;
  const Icon = nodeIcon(node.key);
  const iconColor = domain ? domainColor(domain).text : 'text-module-architect';
  const activityLabel = node.state === 'running' ? '[ NOW ]' : '[ LAST ACTION ]';
  return (
    <div
      className={cn(
        'pointer-events-none absolute inset-x-0 top-0 z-20 opacity-0 translate-y-1',
        'transition-all duration-150 motion-reduce:transition-none',
        'group-hover:pointer-events-auto group-hover:opacity-100 group-hover:translate-y-0',
        'group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-focus-within:translate-y-0',
      )}
    >
      <div
        className={cn(
          'max-h-56 overflow-y-auto rounded-md border bg-surface px-4 py-3 shadow-lg',
          stateRing[node.state],
        )}
      >
        {/* Same header as the node card, so the reveal reads as the card growing. */}
        <div className="flex items-center gap-2">
          <Icon className={cn('h-4 w-4 shrink-0', iconColor)} aria-hidden />
          <span className="flex-1 truncate text-sm font-bold">{node.label}</span>
          <span className={cn('text-micro shrink-0', stateLabelColor[node.state])}>
            {stateLabel[node.state]}
          </span>
        </div>
        <p className="mt-2.5 text-micro text-muted">[ TASK BRIEF ]</p>
        <p className="mt-1 whitespace-pre-wrap font-mono text-xs">{details.brief}</p>
        {details.activity && node.state !== 'idle' && (
          <>
            <p className="mt-2.5 text-micro text-muted">{activityLabel}</p>
            <p className="mt-1 font-mono text-xs text-accent">{details.activity}</p>
          </>
        )}
        {details.dependsOn && details.dependsOn.length > 0 && (
          <>
            <p className="mt-2.5 text-micro text-muted">[ DEPENDS ON ]</p>
            <p className="mt-1 font-mono text-xs text-muted">
              {details.dependsOn.join(', ')}
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function Node({ node, domain }: { node: GraphNode; domain?: string }) {
  const Icon = nodeIcon(node.key);
  // Icon hue carries domain identity; the border/progress carry run state.
  const iconColor = domain ? domainColor(domain).text : 'text-module-architect';
  return (
    <div
      // Focusable only when there is a detail overlay to reveal, so keyboard
      // users can open it via group-focus-within (Tab onto the card).
      tabIndex={node.details ? 0 : undefined}
      className={cn(
        'group relative w-full rounded-md border bg-surface px-4 py-3 transition-all',
        'focus:outline-none focus-visible:ring-1 focus-visible:ring-accent/60',
        stateRing[node.state],
        stateEffect[node.state],
      )}
    >
      {/* Soft expanding ring while the agent works. */}
      {node.state === 'running' && (
        <span
          aria-hidden
          className="pointer-events-none absolute -inset-px rounded-md border border-accent/60 animate-node-ping motion-reduce:hidden"
        />
      )}
      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4 shrink-0', iconColor)} aria-hidden />
        <span className="flex-1 truncate text-sm font-bold">{node.label}</span>
        {/* Keyed remount crossfades the status pill on state changes. */}
        <span
          key={node.state}
          className={cn(
            'text-micro shrink-0 animate-word-in motion-reduce:animate-none',
            stateLabelColor[node.state],
          )}
        >
          {stateLabel[node.state]}
        </span>
      </div>
      {node.sublabel && (
        <p className="mt-1.5 truncate font-mono text-xs text-muted">{node.sublabel}</p>
      )}
      <ProgressBar
        className="mt-2.5"
        color={node.state === 'error' ? 'danger' : 'cyan'}
        hex={node.state === 'done' ? MODULE_COLOR.architect.hex : undefined}
        value={node.state === 'running' ? undefined : node.state === 'done' ? 100 : 0}
      />
      {node.details && <NodeDetailOverlay node={node} domain={domain} />}
    </div>
  );
}

export function AgentGraph({
  orchestrator,
  main,
  subagents,
  reviewer,
  domain,
}: {
  orchestrator: GraphNode;
  main: GraphNode;
  subagents: GraphNode[];
  reviewer?: GraphNode;
  /** Task domain — tints every node's icon with the domain hue. */
  domain?: string;
}) {
  const reduced = useReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  const nodesRef = useRef<Map<string, HTMLElement>>(new Map());
  const registerNode = (key: string) => (el: HTMLElement | null) => {
    if (el) nodesRef.current.set(key, el);
    else nodesRef.current.delete(key);
  };

  // Edge hue: routed domain when known, else the architect violet.
  const flowRgb = domain ? domainColor(domain).rgb : MODULE_COLOR.architect.rgb;

  const edges: FlowEdge[] = [
    { from: 'orchestrator', to: 'main', active: main.state === 'running', done: main.state === 'done' },
    ...subagents.map((node) => ({
      from: 'main',
      to: node.key,
      active: node.state === 'running',
      done: node.state === 'done',
    })),
    ...(reviewer
      ? subagents.map((node) => ({
          from: node.key,
          to: 'reviewer',
          active: reviewer.state === 'running',
          done: reviewer.state === 'done',
        }))
      : []),
  ];

  return (
    <div ref={containerRef} className="relative flex flex-col items-center gap-8">
      <FlowLayer edges={edges} nodesRef={nodesRef} containerRef={containerRef} rgb={flowRgb} />
      <div ref={registerNode('orchestrator')} className="relative w-72 max-w-full">
        <Node node={orchestrator} domain={domain} />
      </div>
      <div ref={registerNode('main')} className="relative w-72 max-w-full">
        <Node node={main} domain={domain} />
      </div>
      {subagents.length > 0 && (
        <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {/* The orchestrator visibly "spawns" its team: assignment cards pop in
              staggered as they stream over the socket. */}
          {subagents.map((node, i) => (
            <motion.div
              key={node.key}
              ref={registerNode(node.key)}
              className="relative hover:z-20 focus-within:z-20"
              initial={reduced ? false : { opacity: 0, y: 10, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={reduced ? { duration: 0 } : { ...SPRING.pop, delay: i * 0.08 }}
            >
              <Node node={node} domain={domain} />
            </motion.div>
          ))}
        </div>
      )}
      {reviewer && (
        <div ref={registerNode('reviewer')} className="relative w-72 max-w-full">
          <Node node={reviewer} domain={domain} />
        </div>
      )}
    </div>
  );
}
