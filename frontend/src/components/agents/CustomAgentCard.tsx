import Link from 'next/link';
import { Bot } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { StatBlock } from '@/components/ui/StatBlock';
import { cn } from '@/lib/cn';
import { domainColor } from '@/lib/agent-colors';
import type { AgentConfig } from '@/types';

interface CustomAgentCardProps {
  agent: AgentConfig;
  /** Tool catalog, used to render assigned-tool labels instead of raw ids. */
  toolLabels: Record<string, string>;
  onDelete: (id: string) => void;
}

/** Show at most this many assigned tools as chips; the rest collapse to "+N". */
const MAX_TOOL_CHIPS = 4;

/** User-defined agent card: identity header, assigned tools, and edit/delete. */
export function CustomAgentCard({ agent, toolLabels, onDelete }: CustomAgentCardProps) {
  const dc = domainColor(agent.domain);
  const shown = agent.tools.slice(0, MAX_TOOL_CHIPS);
  const overflow = agent.tools.length - shown.length;

  return (
    <Card glow domain={agent.domain} className="flex h-full flex-col p-5">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
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
          <p className="min-w-0 flex-1 truncate font-bold text-white">{agent.name}</p>
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

      <div className="mb-4 grid grid-cols-2 gap-3 rounded-md border border-border bg-surface-2 p-3">
        <StatBlock
          size="sm"
          label="Domain"
          value={<span className="capitalize">{agent.domain}</span>}
        />
        <StatBlock size="sm" label="Tools" value={agent.tools.length} />
      </div>

      <div className="mb-4 min-h-[1.75rem]">
        {agent.tools.length === 0 ? (
          <p className="text-[11px] text-muted/70">&gt; No tools assigned.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {shown.map((tool) => (
              <span
                key={tool}
                className="rounded border border-border bg-surface-2 px-2 py-1 text-[11px] text-slate-300"
              >
                {toolLabels[tool] ?? tool}
              </span>
            ))}
            {overflow > 0 && (
              <span className="rounded border border-border/60 px-2 py-1 text-[11px] text-muted">
                +{overflow}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="mt-auto flex justify-end gap-2 border-t border-border/60 pt-3">
        <Link href={`/agents/${agent.id}`}>
          <Button variant="cyan-outline">Edit</Button>
        </Link>
        <Button variant="danger-outline" onClick={() => onDelete(agent.id)}>
          Delete
        </Button>
      </div>
    </Card>
  );
}
