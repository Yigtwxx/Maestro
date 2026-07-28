'use client';

import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import { AGENT_LIMITS } from '@/lib/constants';
import type { AgentDraft, FieldErrors } from '@/lib/agent-wizard';

interface RoutingStepProps {
  draft: AgentDraft;
  errors: FieldErrors;
  onChange: (patch: Partial<AgentDraft>) => void;
}

export function RoutingStep({ draft, errors, onChange }: RoutingStepProps) {
  return (
    <div className="grid gap-5">
      <div className="rounded-lg border border-border bg-surface-2/50 p-4">
        <Switch
          module="agents"
          checked={draft.routable}
          onChange={(routable) => onChange({ routable })}
          label="Let the orchestrator route to this agent"
          hint="Off by default: you can always pick the agent explicitly when starting a task. On, it joins the routing catalog and may be chosen automatically for a matching prompt."
        />
      </div>

      {draft.routable && (
        <div>
          <Textarea
            label="When should this agent be picked?"
            value={draft.routingHint}
            onChange={(e) => onChange({ routingHint: e.target.value })}
            error={errors.routingHint}
            rows={3}
            maxLength={AGENT_LIMITS.routingHint}
            placeholder="Questions about a GitHub project's release cadence, backlog health, or maintenance risk."
            module="agents"
          />
          <p className="mt-1.5 text-xs leading-relaxed text-muted/70">
            This is the only text the orchestrator classifies a prompt against,
            so describe the kind of request rather than the agent. Routable
            agents are capped per account; the newest ones win.{' '}
            <span className="tabular-nums">
              {draft.routingHint.length}/{AGENT_LIMITS.routingHint}
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
