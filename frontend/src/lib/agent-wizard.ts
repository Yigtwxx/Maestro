// Pure draft + validation logic for the agent creation wizard.
//
// Kept free of React so each step's rules can be tested directly (the repo's
// vitest setup covers pure logic only — there is no component test harness).
// Every limit comes from AGENT_LIMITS, which backend
// tests/test_domain_frontend_parity.py compares against the Pydantic schema,
// so a rule here cannot silently diverge from what the API will accept.

import { AGENT_LIMITS } from '@/lib/constants';
import type { AgentConfig, AgentConfigInput, ToolCatalogItem } from '@/types';

export const WIZARD_STEPS = [
  { id: 'identity', label: 'Identity' },
  { id: 'behavior', label: 'Behavior' },
  { id: 'capabilities', label: 'Capabilities' },
  { id: 'routing', label: 'Routing' },
  { id: 'preview', label: 'Preview' },
] as const;

export type WizardStep = (typeof WIZARD_STEPS)[number]['id'];

export interface AgentDraft {
  name: string;
  domain: string;
  description: string;
  systemPrompt: string;
  outputFormat: string;
  tools: string[];
  routable: boolean;
  routingHint: string;
}

export type FieldErrors = Partial<Record<keyof AgentDraft, string>>;

export const EMPTY_DRAFT: AgentDraft = {
  name: '',
  domain: 'general',
  description: '',
  systemPrompt: '',
  outputFormat: '',
  tools: [],
  routable: false,
  routingHint: '',
};

/** Seed a draft from a stored agent. Used by the edit page. */
export function draftFromAgent(agent: AgentConfig): AgentDraft {
  return {
    name: agent.name,
    domain: agent.domain,
    description: agent.description ?? '',
    systemPrompt: agent.system_prompt,
    outputFormat: agent.output_format ?? '',
    tools: agent.tools ?? [],
    routable: agent.routable ?? false,
    routingHint: agent.routing_hint ?? '',
  };
}

function tooLong(value: string, max: number): string | undefined {
  return value.length > max ? `Too long — ${value.length}/${max} characters.` : undefined;
}

/**
 * Errors for one step. An empty object means the step may be left.
 *
 * Only blocking problems belong here: a tool with a missing key is a warning
 * the capabilities step renders inline, not a reason to trap the user — the
 * squad still runs and reports the gap (CLAUDE.md §8).
 */
export function validateStep(step: WizardStep, draft: AgentDraft): FieldErrors {
  const errors: FieldErrors = {};
  if (step === 'identity') {
    if (!draft.name.trim()) {
      errors.name = 'Give the agent a name.';
    } else {
      errors.name = tooLong(draft.name, AGENT_LIMITS.name);
    }
    if (!draft.domain.trim()) errors.domain = 'Pick a domain.';
    errors.description = tooLong(draft.description, AGENT_LIMITS.description);
  }
  if (step === 'behavior') {
    if (draft.systemPrompt.trim().length < AGENT_LIMITS.systemPromptMin) {
      errors.systemPrompt = 'Describe what this agent should do.';
    } else {
      errors.systemPrompt = tooLong(draft.systemPrompt, AGENT_LIMITS.systemPrompt);
    }
    errors.outputFormat = tooLong(draft.outputFormat, AGENT_LIMITS.outputFormat);
  }
  if (step === 'routing') {
    // A routable agent with no hint is unroutable in practice: routing_hint is
    // the only text the orchestrator classifies a prompt against.
    if (draft.routable && !draft.routingHint.trim()) {
      errors.routingHint = 'Describe when the orchestrator should pick this agent.';
    } else {
      errors.routingHint = tooLong(draft.routingHint, AGENT_LIMITS.routingHint);
    }
  }
  // Drop the undefined slots so callers can treat the object as "no errors".
  return Object.fromEntries(
    Object.entries(errors).filter(([, message]) => Boolean(message)),
  ) as FieldErrors;
}

export function hasErrors(errors: FieldErrors): boolean {
  return Object.keys(errors).length > 0;
}

/** The first step that still has a blocking error, or undefined if all pass. */
export function firstInvalidStep(draft: AgentDraft): WizardStep | undefined {
  return WIZARD_STEPS.map((s) => s.id).find((id) =>
    hasErrors(validateStep(id, draft)),
  );
}

export function draftToInput(draft: AgentDraft): AgentConfigInput {
  return {
    name: draft.name.trim(),
    domain: draft.domain,
    system_prompt: draft.systemPrompt.trim(),
    tools: draft.tools,
    description: draft.description.trim(),
    output_format: draft.outputFormat.trim(),
    routable: draft.routable,
    // A hint on a non-routable agent is dead metadata that would still be
    // stored and shown back; drop it so the saved record matches the toggle.
    routing_hint: draft.routable ? draft.routingHint.trim() : '',
  };
}

/**
 * Why a selected tool will not actually run, or undefined if it will.
 * Advisory only — see validateStep.
 */
export function toolWarning(tool: ToolCatalogItem): string | undefined {
  if (!tool.available) {
    return 'Disabled on this deployment — the agent will run without it.';
  }
  if (tool.kind === 'declarative') {
    return 'Performed by the model itself; it makes no external call.';
  }
  if (tool.connected || tool.providers.length === 0) return undefined;
  if (tool.keyless) {
    return 'Works without a key at a lower rate limit. Add one to raise it.';
  }
  return 'Needs a key you have not added yet — the agent will fall back to web search.';
}
