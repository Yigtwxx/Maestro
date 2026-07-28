'use client';

import { useMemo } from 'react';
import { Checkbox } from '@/components/ui/Checkbox';
import { cn } from '@/lib/cn';
import { toolWarning } from '@/lib/agent-wizard';
import { ConnectedKeysPanel } from '@/components/agents/wizard/ConnectedKeysPanel';
import type { AgentDraft } from '@/lib/agent-wizard';
import type { ToolCatalogItem } from '@/types';

interface CapabilitiesStepProps {
  draft: AgentDraft;
  tools: ToolCatalogItem[];
  onChange: (patch: Partial<AgentDraft>) => void;
}

const GROUPS = [
  {
    kind: 'executable' as const,
    title: '[ EXECUTABLE TOOLS ]',
    blurb:
      'Real calls the agent makes during a run — searches, fetches, connected APIs.',
  },
  {
    kind: 'declarative' as const,
    title: '[ NATIVE ABILITIES ]',
    blurb:
      'Performed by the model in its own reasoning. Declaring one shapes the plan; it makes no external call.',
  },
];

export function CapabilitiesStep({
  draft,
  tools,
  onChange,
}: CapabilitiesStepProps) {
  const selectedTools = useMemo(
    () => tools.filter((tool) => draft.tools.includes(tool.id)),
    [tools, draft.tools],
  );

  const toggle = (id: string, on: boolean) => {
    onChange({
      tools: on
        ? [...draft.tools, id]
        : draft.tools.filter((entry) => entry !== id),
    });
  };

  return (
    <div className="grid gap-6">
      {GROUPS.map((group) => {
        const groupTools = tools.filter((tool) => tool.kind === group.kind);
        if (groupTools.length === 0) return null;
        return (
          <section key={group.kind}>
            <p className="text-micro text-module-agents">{group.title}</p>
            <p className="mb-3 mt-1 text-xs text-muted/80">{group.blurb}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {groupTools.map((tool) => {
                const warning = toolWarning(tool);
                const checked = draft.tools.includes(tool.id);
                return (
                  <div
                    key={tool.id}
                    className={cn(
                      'rounded-md border p-3 transition-colors',
                      checked
                        ? 'border-module-agents/50 bg-module-agents/5'
                        : 'border-border bg-surface-2/50',
                      !tool.available && 'opacity-60',
                    )}
                  >
                    <Checkbox
                      module="agents"
                      checked={checked}
                      onChange={(e) => toggle(tool.id, e.target.checked)}
                      label={tool.label}
                      hint={tool.description}
                    />
                    {warning && checked && (
                      <p
                        className={cn(
                          'mt-2 pl-[26px] text-xs leading-snug',
                          tool.available ? 'text-muted/80' : 'text-warning',
                        )}
                      >
                        {warning}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}

      <ConnectedKeysPanel selected={selectedTools} />

      {draft.tools.length === 0 && (
        <p className="text-xs text-muted/80">
          An agent with no tools still works — it answers from the model&apos;s own
          knowledge. Add tools when it needs facts it cannot already have.
        </p>
      )}
    </div>
  );
}
