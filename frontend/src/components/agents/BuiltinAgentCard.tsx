import { Bot } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { cn } from '@/lib/cn';
import { domainColor } from '@/lib/agent-colors';
import type { BuiltinAgent } from '@/types';

interface BuiltinAgentCardProps {
  agent: BuiltinAgent;
}

/**
 * Display card for one built-in domain squad. Surfaces the rich data the
 * backend already ships — description, capabilities, and the internal team —
 * that the registry previously collapsed into a bare name chip.
 */
export function BuiltinAgentCard({ agent }: BuiltinAgentCardProps) {
  const dc = domainColor(agent.domain);
  return (
    <Card glow domain={agent.domain} className="flex h-full flex-col p-5">
      <div className="mb-2.5 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border',
              dc.border,
              dc.bg,
            )}
            aria-hidden
          >
            <Bot className={cn('h-5 w-5', dc.text)} />
          </span>
          <p className="font-bold leading-tight text-white">{agent.name}</p>
        </div>
        <span
          className={cn(
            'text-micro inline-flex shrink-0 items-center gap-1.5 capitalize',
            dc.text,
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', dc.dot)} aria-hidden />
          {agent.domain}
        </span>
      </div>

      <p className="mb-3 text-[13px] leading-relaxed text-slate-400">
        {agent.description}
      </p>

      {agent.capabilities.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {agent.capabilities.map((capability) => (
            <span
              key={capability}
              className="rounded border border-border bg-surface-2 px-2 py-1 text-[11px] text-slate-300"
            >
              {capability}
            </span>
          ))}
        </div>
      )}

      <div className="mt-auto space-y-2 border-t border-border/60 pt-3">
        {agent.team.length > 0 && (
          <p className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-[11px] text-muted">
            <span className="text-micro shrink-0 pt-px">[ TEAM ]</span>
            {agent.team.map((member) => member.name).join(' · ')}
          </p>
        )}
        <p className="flex items-center gap-1.5 text-[11px] text-muted">
          <span className="text-micro shrink-0">[ TOOLS ]</span>
          {agent.tools.length} available
        </p>
      </div>
    </Card>
  );
}
