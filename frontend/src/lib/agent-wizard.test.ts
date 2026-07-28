import { describe, expect, it } from 'vitest';
import {
  EMPTY_DRAFT,
  draftFromAgent,
  draftToInput,
  firstInvalidStep,
  hasErrors,
  toolWarning,
  validateStep,
  type AgentDraft,
} from '@/lib/agent-wizard';
import { AGENT_LIMITS } from '@/lib/constants';
import type { AgentConfig, ToolCatalogItem } from '@/types';

function draft(overrides: Partial<AgentDraft> = {}): AgentDraft {
  return {
    ...EMPTY_DRAFT,
    name: 'Repo Watcher',
    systemPrompt: 'Track releases for a repository.',
    ...overrides,
  };
}

function tool(overrides: Partial<ToolCatalogItem> = {}): ToolCatalogItem {
  return {
    id: 'web_search',
    label: 'Web Search',
    description: 'Search the web.',
    kind: 'executable',
    providers: [],
    keyless: false,
    connected: true,
    available: true,
    ...overrides,
  };
}

describe('validateStep — identity', () => {
  it('requires a name', () => {
    expect(validateStep('identity', draft({ name: '' })).name).toBeDefined();
  });

  it('rejects a whitespace-only name', () => {
    expect(validateStep('identity', draft({ name: '   ' })).name).toBeDefined();
  });

  it('accepts a name exactly at the limit', () => {
    const name = 'a'.repeat(AGENT_LIMITS.name);
    expect(validateStep('identity', draft({ name })).name).toBeUndefined();
  });

  it('rejects a name one character over the limit', () => {
    const name = 'a'.repeat(AGENT_LIMITS.name + 1);
    expect(validateStep('identity', draft({ name })).name).toBeDefined();
  });

  it('rejects an over-long description', () => {
    const description = 'd'.repeat(AGENT_LIMITS.description + 1);
    expect(
      validateStep('identity', draft({ description })).description,
    ).toBeDefined();
  });

  it('accepts an empty description — it is optional', () => {
    expect(
      validateStep('identity', draft({ description: '' })).description,
    ).toBeUndefined();
  });
});

describe('validateStep — behavior', () => {
  it('requires a system prompt', () => {
    expect(
      validateStep('behavior', draft({ systemPrompt: '' })).systemPrompt,
    ).toBeDefined();
  });

  it('rejects a whitespace-only system prompt', () => {
    expect(
      validateStep('behavior', draft({ systemPrompt: '  \n ' })).systemPrompt,
    ).toBeDefined();
  });

  it('accepts a system prompt exactly at the limit', () => {
    const systemPrompt = 'p'.repeat(AGENT_LIMITS.systemPrompt);
    expect(
      validateStep('behavior', draft({ systemPrompt })).systemPrompt,
    ).toBeUndefined();
  });

  it('rejects a system prompt one character over the limit', () => {
    const systemPrompt = 'p'.repeat(AGENT_LIMITS.systemPrompt + 1);
    expect(
      validateStep('behavior', draft({ systemPrompt })).systemPrompt,
    ).toBeDefined();
  });

  it('rejects an over-long output format', () => {
    const outputFormat = 'o'.repeat(AGENT_LIMITS.outputFormat + 1);
    expect(
      validateStep('behavior', draft({ outputFormat })).outputFormat,
    ).toBeDefined();
  });
});

describe('validateStep — routing', () => {
  it('requires a hint once the agent is routable', () => {
    const errors = validateStep(
      'routing',
      draft({ routable: true, routingHint: '' }),
    );
    expect(errors.routingHint).toBeDefined();
  });

  it('does not require a hint while the agent is not routable', () => {
    const errors = validateStep(
      'routing',
      draft({ routable: false, routingHint: '' }),
    );
    expect(errors.routingHint).toBeUndefined();
  });

  it('rejects an over-long hint', () => {
    const routingHint = 'h'.repeat(AGENT_LIMITS.routingHint + 1);
    expect(
      validateStep('routing', draft({ routable: true, routingHint })).routingHint,
    ).toBeDefined();
  });
});

describe('validateStep — capabilities and preview', () => {
  it('never blocks on capabilities: a toolless agent is legitimate', () => {
    expect(hasErrors(validateStep('capabilities', draft({ tools: [] })))).toBe(
      false,
    );
  });

  it('never blocks on preview', () => {
    expect(hasErrors(validateStep('preview', draft()))).toBe(false);
  });
});

describe('firstInvalidStep', () => {
  it('returns undefined for a complete draft', () => {
    expect(firstInvalidStep(draft())).toBeUndefined();
  });

  it('reports the earliest broken step, not the latest', () => {
    const broken = draft({ name: '', routable: true, routingHint: '' });
    expect(firstInvalidStep(broken)).toBe('identity');
  });

  it('finds a later step when the earlier ones pass', () => {
    expect(firstInvalidStep(draft({ routable: true, routingHint: '' }))).toBe(
      'routing',
    );
  });
});

describe('draftToInput', () => {
  it('trims text fields and maps to the API shape', () => {
    const input = draftToInput(
      draft({
        name: '  Repo Watcher  ',
        systemPrompt: '  Watch it.  ',
        description: '  Tracks releases.  ',
        domain: 'opensource',
        tools: ['repo_intel'],
      }),
    );
    expect(input).toEqual({
      name: 'Repo Watcher',
      domain: 'opensource',
      system_prompt: 'Watch it.',
      tools: ['repo_intel'],
      custom_api_tool_ids: [],
      description: 'Tracks releases.',
      output_format: '',
      routable: false,
      routing_hint: '',
    });
  });

  it('keeps the routing hint when the agent is routable', () => {
    const input = draftToInput(
      draft({ routable: true, routingHint: 'Release questions' }),
    );
    expect(input.routing_hint).toBe('Release questions');
    expect(input.routable).toBe(true);
  });

  it('drops a hint left behind after routable was switched off', () => {
    const input = draftToInput(
      draft({ routable: false, routingHint: 'Release questions' }),
    );
    expect(input.routing_hint).toBe('');
  });
});

describe('draftFromAgent', () => {
  it('round-trips every field the wizard owns', () => {
    const agent: AgentConfig = {
      id: 'a1',
      name: 'Repo Watcher',
      domain: 'opensource',
      system_prompt: 'Watch it.',
      tools: ['repo_intel'],
      description: 'Tracks releases.',
      routing_hint: 'Release questions',
      output_format: 'A bullet list.',
      routable: true,
      custom_api_tool_ids: ['endpoint-1'],
      type: 'custom',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };
    expect(draftToInput(draftFromAgent(agent))).toEqual({
      name: 'Repo Watcher',
      domain: 'opensource',
      system_prompt: 'Watch it.',
      tools: ['repo_intel'],
      custom_api_tool_ids: ['endpoint-1'],
      description: 'Tracks releases.',
      output_format: 'A bullet list.',
      routable: true,
      routing_hint: 'Release questions',
    });
  });
});

describe('draftToInput — custom API endpoints', () => {
  it('sends endpoint ids in their own field, never mixed into tools', () => {
    const input = draftToInput(
      draft({ tools: ['web_search'], customApiToolIds: ['endpoint-1'] }),
    );
    expect(input.tools).toEqual(['web_search']);
    expect(input.custom_api_tool_ids).toEqual(['endpoint-1']);
  });

  it('defaults to no endpoints', () => {
    expect(draftToInput(draft()).custom_api_tool_ids).toEqual([]);
  });
});

describe('toolWarning', () => {
  it('is silent for a usable executable tool', () => {
    expect(toolWarning(tool())).toBeUndefined();
  });

  it('flags a tool the operator disabled', () => {
    expect(toolWarning(tool({ available: false }))).toMatch(/Disabled/);
  });

  it('explains that a declarative tool makes no external call', () => {
    expect(toolWarning(tool({ id: 'summarize', kind: 'declarative' }))).toMatch(
      /model itself/,
    );
  });

  it('flags a connected tool with no key', () => {
    const missing = tool({
      id: 'social_search',
      providers: ['x'],
      connected: false,
    });
    expect(toolWarning(missing)).toMatch(/fall back to web search/);
  });

  it('softens the message for a keyless tool', () => {
    const keyless = tool({
      id: 'repo_intel',
      providers: ['github'],
      connected: false,
      keyless: true,
    });
    expect(toolWarning(keyless)).toMatch(/Works without a key/);
  });

  it('says nothing about keys for a tool that needs none', () => {
    expect(toolWarning(tool({ connected: false, providers: [] }))).toBeUndefined();
  });

  it('reports the operator switch before the missing key', () => {
    const both = tool({
      id: 'social_search',
      providers: ['x'],
      connected: false,
      available: false,
    });
    expect(toolWarning(both)).toMatch(/Disabled/);
  });
});
