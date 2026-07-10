'use client';

import { cn } from '@/lib/cn';
import { domainColor } from '@/lib/agent-colors';
import type { BuiltinAgent } from '@/types';

interface AgentCatalogProps {
  agents: BuiltinAgent[];
  /** Selected domain id; null = automatic routing; undefined = no choice yet. */
  selected: string | null | undefined;
  onSelect: (domain: string | null) => void;
  disabled?: boolean;
}

const cardBase =
  'flex h-full flex-col rounded-lg border bg-surface p-4 text-left transition-all ' +
  'disabled:cursor-not-allowed disabled:opacity-60';

/** Domain agent picker: one card per expert plus automatic routing. */
export function AgentCatalog({
  agents,
  selected,
  onSelect,
  disabled,
}: AgentCatalogProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
      <button
        type="button"
        aria-pressed={selected === null}
        disabled={disabled}
        onClick={() => onSelect(null)}
        className={cn(
          cardBase,
          selected === null
            ? 'border-accent shadow-glow-cyan'
            : 'border-border hover:border-border-bright',
        )}
      >
        <span className="text-sm font-bold text-accent">
          Automatic (Orchestrator)
        </span>
        <span className="mt-1 text-xs text-muted">
          If you are not sure which expert to pick, just write your prompt;
          the Orchestrator analyzes the task and routes it to the best expert.
        </span>
      </button>

      {agents.map((agent) => {
        const isSelected = selected === agent.domain;
        const dc = domainColor(agent.domain);
        return (
          <button
            key={agent.id}
            type="button"
            aria-pressed={isSelected}
            disabled={disabled}
            onClick={() => onSelect(agent.domain)}
            className={cn(
              cardBase,
              isSelected
                ? cn(dc.borderSelected, dc.glow)
                : cn('border-border', dc.borderHover, dc.glowHover),
            )}
          >
            <span className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-bold text-white">{agent.name}</span>
              <span className={cn('text-micro inline-flex items-center gap-1.5', dc.text)}>
                <span className={cn('h-1.5 w-1.5 rounded-full', dc.dot)} aria-hidden />
                {agent.domain}
              </span>
            </span>
            <span className="mt-1 text-xs text-muted">{agent.description}</span>
            <span className="mt-2 flex flex-wrap gap-1">
              {agent.capabilities.map((capability) => (
                <span
                  key={capability}
                  className="text-micro rounded border border-border bg-surface-2 px-1.5 py-0.5 text-slate-300"
                >
                  {capability}
                </span>
              ))}
            </span>
            {agent.team.length > 0 && (
              <span className="text-micro mt-auto pt-2 text-muted">
                [ TAKIM ] {agent.team.map((member) => member.name).join(' · ')}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
