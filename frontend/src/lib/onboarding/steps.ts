// First-run onboarding step definitions. The overlay
// (components/onboarding/OnboardingCoachmark.tsx) walks this list, anchoring each
// coachmark to the DOM element carrying `data-onboarding="<targetId>"` on the
// matching `route`. Keep targetId strings in sync with the anchors added in the
// Sidebar, the API-keys page and the Architect page.

import type { ModuleKey } from '@/lib/module-colors';

/** Context the step's `skipIf` predicate is evaluated against. */
export interface OnboardingContext {
  /** True when the user already has at least one active BYOK key. */
  hasApiKey: boolean;
}

/** Where the bubble sits relative to its anchor element. */
export type CoachmarkPlacement = 'top' | 'bottom' | 'left' | 'right';

export interface OnboardingStep {
  id: string;
  /** Pathname the anchor lives on; the coachmark hides on other routes. */
  route: string;
  /** Value of the target's `data-onboarding` attribute. */
  targetId: string;
  title: string;
  body: string;
  placement: CoachmarkPlacement;
  /** Neon hue for the bubble chrome. */
  module: ModuleKey;
  /** When true, the step is dropped from the resolved list for this user. */
  skipIf?: (ctx: OnboardingContext) => boolean;
}

// Users who already connected a key skip the "go add a key" leg and start the
// tour at expert selection.
const skipWhenKeyed = (ctx: OnboardingContext): boolean => ctx.hasApiKey;

export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  {
    id: 'connect-key',
    route: '/architect',
    targetId: 'nav-api-keys',
    title: 'First, connect an AI key',
    body: 'Maestro runs on your own key (BYOK). Head to the API Keys screen from here.',
    placement: 'right',
    module: 'api-keys',
    skipIf: skipWhenKeyed,
  },
  {
    id: 'add-key',
    route: '/settings/api-keys',
    targetId: 'add-key',
    title: 'Add your first key',
    body: 'Pick a provider, paste your key and save. The key is stored encrypted.',
    placement: 'top',
    module: 'api-keys',
    skipIf: skipWhenKeyed,
  },
  {
    id: 'back-to-architect',
    route: '/settings/api-keys',
    targetId: 'nav-architect',
    title: 'You’re ready',
    body: 'Now head back to the Architect screen to run your first task.',
    placement: 'right',
    module: 'architect',
    skipIf: skipWhenKeyed,
  },
  {
    id: 'pick-expert',
    route: '/architect',
    targetId: 'agent-catalog',
    title: 'Pick an expert',
    body: 'Choose an expert that fits your task. Not sure? Automatic (Orchestrator) routes it for you.',
    placement: 'top',
    module: 'architect',
  },
  {
    id: 'write-task',
    route: '/architect',
    targetId: 'task-prompt',
    title: 'Write your task',
    body: 'Describe what you want done here in a few sentences.',
    placement: 'left',
    module: 'architect',
  },
  {
    id: 'start-task',
    route: '/architect',
    targetId: 'start-task',
    title: 'Start your first task',
    body: 'When ready, hit Start Task — the agents begin working and you watch the stream live.',
    placement: 'left',
    module: 'architect',
  },
];

/** The steps this user will actually see, in order, after applying `skipIf`. */
export function resolveSteps(ctx: OnboardingContext): OnboardingStep[] {
  return ONBOARDING_STEPS.filter((step) => !step.skipIf?.(ctx));
}
