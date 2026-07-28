'use client';

import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Stepper } from '@/components/ui/Stepper';
import { IdentityStep } from '@/components/agents/wizard/steps/IdentityStep';
import { BehaviorStep } from '@/components/agents/wizard/steps/BehaviorStep';
import { CapabilitiesStep } from '@/components/agents/wizard/steps/CapabilitiesStep';
import { RoutingStep } from '@/components/agents/wizard/steps/RoutingStep';
import { PreviewStep } from '@/components/agents/wizard/steps/PreviewStep';
import {
  EMPTY_DRAFT,
  WIZARD_STEPS,
  draftToInput,
  firstInvalidStep,
  hasErrors,
  validateStep,
  type AgentDraft,
} from '@/lib/agent-wizard';
import type { AgentConfigInput, ToolCatalogItem } from '@/types';

interface AgentWizardProps {
  tools: ToolCatalogItem[];
  /** Seeded on the edit page. Must carry every field — see the note below. */
  initial?: AgentDraft;
  submitLabel: string;
  onSubmit: (input: AgentConfigInput) => Promise<void>;
}

const LAST = WIZARD_STEPS.length - 1;

/**
 * Five-step agent builder, shared by create and edit.
 *
 * `initial` is the whole draft rather than a subset on purpose: the wizard
 * submits every field on save, so seeding a partial draft would blank the
 * fields it omitted. Use `draftFromAgent` to build it.
 */
export function AgentWizard({
  tools,
  initial,
  submitLabel,
  onSubmit,
}: AgentWizardProps) {
  const [draft, setDraft] = useState<AgentDraft>(initial ?? EMPTY_DRAFT);
  const [step, setStep] = useState(0);
  // How far the user has legitimately reached. Editing an existing agent starts
  // fully unlocked — every step already holds saved, valid values.
  const [furthest, setFurthest] = useState(initial ? LAST : 0);
  // Errors stay hidden until the user tries to advance, so a half-typed name is
  // not scolded mid-keystroke.
  const [showErrors, setShowErrors] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const stepId = WIZARD_STEPS[step].id;
  const stepErrors = useMemo(
    () => validateStep(stepId, draft),
    [stepId, draft],
  );
  const visibleErrors = showErrors ? stepErrors : {};

  const patch = (values: Partial<AgentDraft>) => {
    setDraft((prev) => ({ ...prev, ...values }));
  };

  const goTo = (next: number) => {
    setStep(next);
    setShowErrors(false);
    setError(undefined);
  };

  const next = () => {
    if (hasErrors(stepErrors)) {
      setShowErrors(true);
      return;
    }
    const target = Math.min(step + 1, LAST);
    setFurthest((prev) => Math.max(prev, target));
    goTo(target);
  };

  const handleSubmit = async () => {
    // Re-check every step, not just this one: the user can jump backwards and
    // empty a field that was valid when they passed it.
    const broken = firstInvalidStep(draft);
    if (broken) {
      const index = WIZARD_STEPS.findIndex((s) => s.id === broken);
      setStep(index);
      setShowErrors(true);
      setError('Some required fields still need attention.');
      return;
    }
    setError(undefined);
    setSaving(true);
    try {
      await onSubmit(draftToInput(draft));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-5 rounded-lg border border-module-agents/30 bg-surface p-5">
      <Stepper
        steps={WIZARD_STEPS.map((s) => ({ id: s.id, label: s.label }))}
        current={step}
        furthest={furthest}
        onStep={goTo}
        module="agents"
      />

      <div className="min-h-[18rem] border-t border-border/60 pt-5">
        {stepId === 'identity' && (
          <IdentityStep draft={draft} errors={visibleErrors} onChange={patch} />
        )}
        {stepId === 'behavior' && (
          <BehaviorStep draft={draft} errors={visibleErrors} onChange={patch} />
        )}
        {stepId === 'capabilities' && (
          <CapabilitiesStep draft={draft} tools={tools} onChange={patch} />
        )}
        {stepId === 'routing' && (
          <RoutingStep draft={draft} errors={visibleErrors} onChange={patch} />
        )}
        {stepId === 'preview' && <PreviewStep draft={draft} tools={tools} />}
      </div>

      {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}

      <div className="flex items-center justify-between gap-3 border-t border-border/60 pt-4">
        <Button
          type="button"
          variant="ghost"
          onClick={() => goTo(Math.max(step - 1, 0))}
          disabled={step === 0 || saving}
        >
          Back
        </Button>
        {step < LAST ? (
          <Button type="button" variant="solid" module="agents" onClick={next}>
            Next
          </Button>
        ) : (
          <Button
            type="button"
            variant="solid"
            module="agents"
            loading={saving}
            onClick={() => void handleSubmit()}
          >
            {submitLabel}
          </Button>
        )}
      </div>
    </div>
  );
}
