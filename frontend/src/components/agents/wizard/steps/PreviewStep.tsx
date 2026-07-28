'use client';

import { Badge } from '@/components/ui/Badge';
import { AGENT_LOCALE } from '@/lib/agent-locale';
import { toolWarning } from '@/lib/agent-wizard';
import type { AgentDraft } from '@/lib/agent-wizard';
import type { ToolCatalogItem } from '@/types';

interface PreviewStepProps {
  draft: AgentDraft;
  tools: ToolCatalogItem[];
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b border-border/60 py-3 last:border-b-0 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="text-micro text-muted">{label}</dt>
      <dd className="min-w-0 text-sm text-white">{children}</dd>
    </div>
  );
}

export function PreviewStep({ draft, tools }: PreviewStepProps) {
  const selected = tools.filter((tool) => draft.tools.includes(tool.id));
  const degraded = selected.filter((tool) => !tool.available || !tool.connected);

  return (
    <div className="grid gap-5">
      <dl className="rounded-lg border border-border bg-surface-2/50 px-4">
        <Row label="Name">{draft.name || <span className="text-muted">—</span>}</Row>
        <Row label="Domain">
          {AGENT_LOCALE[draft.domain]?.name ?? draft.domain}
        </Row>
        {draft.description && <Row label="Description">{draft.description}</Row>}
        <Row label="Tools">
          {selected.length === 0 ? (
            <span className="text-muted">
              None — answers from the model&apos;s own knowledge.
            </span>
          ) : (
            <span className="flex flex-wrap gap-1.5">
              {selected.map((tool) => (
                <Badge key={tool.id} module="agents">
                  {tool.label}
                </Badge>
              ))}
            </span>
          )}
        </Row>
        <Row label="Routing">
          {draft.routable ? (
            <>
              Auto-routed.{' '}
              <span className="text-muted">{draft.routingHint}</span>
            </>
          ) : (
            <span className="text-muted">
              Manual — pick this agent when starting a task.
            </span>
          )}
        </Row>
        {draft.outputFormat && (
          <Row label="Output format">
            <span className="whitespace-pre-wrap text-muted">
              {draft.outputFormat}
            </span>
          </Row>
        )}
      </dl>

      <div>
        <p className="text-micro text-muted">[ SYSTEM PROMPT ]</p>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-surface-2 p-3 font-mono text-xs leading-relaxed text-white">
          {draft.systemPrompt || '—'}
        </pre>
        <p className="mt-1.5 text-xs text-muted/70">
          Runs sandboxed inside the platform&apos;s own instructions and is
          re-scanned on every save.
        </p>
      </div>

      {degraded.length > 0 && (
        <p className="rounded-md border border-warning/40 bg-warning/5 p-3 text-xs leading-relaxed text-warning">
          {degraded.map((tool) => `${tool.label}: ${toolWarning(tool)}`).join(' ')}
        </p>
      )}
    </div>
  );
}
