'use client';

import { Textarea } from '@/components/ui/Textarea';
import { AGENT_LIMITS } from '@/lib/constants';
import { cn } from '@/lib/cn';
import type { AgentDraft, FieldErrors } from '@/lib/agent-wizard';

interface BehaviorStepProps {
  draft: AgentDraft;
  errors: FieldErrors;
  onChange: (patch: Partial<AgentDraft>) => void;
}

/** Warn before the hard stop, so a long prompt is not lost at the limit. */
const WARN_AT = 0.9;

function Counter({ value, max }: { value: number; max: number }) {
  const near = value > max * WARN_AT;
  return (
    <span
      className={cn('tabular-nums', near ? 'text-warning' : 'text-muted/70')}
      aria-live={near ? 'polite' : 'off'}
    >
      {value}/{max}
    </span>
  );
}

export function BehaviorStep({ draft, errors, onChange }: BehaviorStepProps) {
  return (
    <div className="grid gap-5">
      <div>
        <Textarea
          label="System prompt"
          value={draft.systemPrompt}
          onChange={(e) => onChange({ systemPrompt: e.target.value })}
          error={errors.systemPrompt}
          rows={10}
          maxLength={AGENT_LIMITS.systemPrompt}
          placeholder="You are a release analyst. For any repository you are given, report the release cadence, the open issue backlog, and anything that looks stalled…"
          module="agents"
        />
        <p className="mt-1.5 flex items-center justify-between gap-3 text-xs text-muted/70">
          <span>
            Scanned for injection patterns on save and sandboxed at run time, so
            it cannot override the platform&apos;s own instructions.
          </span>
          <Counter
            value={draft.systemPrompt.length}
            max={AGENT_LIMITS.systemPrompt}
          />
        </p>
      </div>

      <div>
        <Textarea
          label="Output format (optional)"
          value={draft.outputFormat}
          onChange={(e) => onChange({ outputFormat: e.target.value })}
          error={errors.outputFormat}
          rows={4}
          maxLength={AGENT_LIMITS.outputFormat}
          placeholder="A markdown table of releases, then a short 'Risks' section."
          module="agents"
        />
        <p className="mt-1.5 flex items-center justify-between gap-3 text-xs text-muted/70">
          <span>
            How the answer should be shaped. Left empty, the domain&apos;s own
            default format is used.
          </span>
          <Counter
            value={draft.outputFormat.length}
            max={AGENT_LIMITS.outputFormat}
          />
        </p>
      </div>
    </div>
  );
}
