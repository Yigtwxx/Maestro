'use client';

import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { AGENT_LOCALE } from '@/lib/agent-locale';
import { AGENT_LIMITS, AGENT_DOMAINS } from '@/lib/constants';
import type { AgentDraft, FieldErrors } from '@/lib/agent-wizard';

interface IdentityStepProps {
  draft: AgentDraft;
  errors: FieldErrors;
  onChange: (patch: Partial<AgentDraft>) => void;
}

// The domain a custom agent inherits its planning methodology, expertise and
// review rubric from. Labelled from AGENT_LOCALE rather than shown as the raw
// backend id, which is what the previous form did.
const DOMAIN_OPTIONS = AGENT_DOMAINS.map((id) => ({
  value: id,
  label: AGENT_LOCALE[id]?.name ?? id,
}));

export function IdentityStep({ draft, errors, onChange }: IdentityStepProps) {
  const domainCopy = AGENT_LOCALE[draft.domain]?.description;
  return (
    <div className="grid gap-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Input
          label="Agent name"
          value={draft.name}
          onChange={(e) => onChange({ name: e.target.value })}
          error={errors.name}
          placeholder="E.g. Release Watcher"
          maxLength={AGENT_LIMITS.name}
          module="agents"
        />
        <Select
          label="Domain"
          value={draft.domain}
          onChange={(e) => onChange({ domain: e.target.value })}
          error={errors.domain}
          options={DOMAIN_OPTIONS}
          module="agents"
        />
      </div>
      {domainCopy && (
        <p className="-mt-2 text-xs leading-relaxed text-muted/80">
          Your agent inherits this domain&apos;s planning methodology and review
          rubric. {domainCopy}
        </p>
      )}

      <div>
        <Input
          label="Short description (optional)"
          value={draft.description}
          onChange={(e) => onChange({ description: e.target.value })}
          error={errors.description}
          placeholder="One line describing what this agent is for"
          maxLength={AGENT_LIMITS.description}
          module="agents"
        />
        <p className="mt-1.5 text-xs text-muted/70">
          Shown on the agent card. {draft.description.length}/
          {AGENT_LIMITS.description}
        </p>
      </div>
    </div>
  );
}
