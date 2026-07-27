import { describe, it, expect } from 'vitest';
import {
  AI_PROVIDERS,
  BRAIN_CHAT_PROVIDERS,
  BRAIN_KEY_PROVIDERS,
  groupProviders,
  PROVIDER_MAP,
  PROVIDERS,
  SERVICE_PROVIDERS,
  TASK_PROVIDERS,
} from '@/lib/providers';

describe('PROVIDER_MAP', () => {
  it('has one entry per provider, keyed by id', () => {
    expect(Object.keys(PROVIDER_MAP)).toHaveLength(PROVIDERS.length);
    for (const provider of PROVIDERS) {
      expect(PROVIDER_MAP[provider.id]).toBe(provider);
    }
  });
});

describe('category partitions', () => {
  it('AI and service partitions are complete and disjoint', () => {
    expect(AI_PROVIDERS.every((p) => p.category === 'ai')).toBe(true);
    expect(SERVICE_PROVIDERS.every((p) => p.category === 'service')).toBe(true);
    expect(AI_PROVIDERS.length + SERVICE_PROVIDERS.length).toBe(PROVIDERS.length);
  });
});

describe('BRAIN_KEY_PROVIDERS', () => {
  it('is the AI providers minus keyless local Ollama', () => {
    const ids = BRAIN_KEY_PROVIDERS.map((p) => p.id);
    expect(ids).not.toContain('ollama');
    expect(BRAIN_KEY_PROVIDERS.every((p) => p.category === 'ai')).toBe(true);
    // Ollama is the only AI provider excluded, so the counts differ by exactly one.
    expect(BRAIN_KEY_PROVIDERS.length).toBe(AI_PROVIDERS.length - 1);
    expect(AI_PROVIDERS.some((p) => p.id === 'ollama')).toBe(true);
  });
});

describe('TASK_PROVIDERS and BRAIN_CHAT_PROVIDERS', () => {
  it('task providers are chat-capable AI providers', () => {
    expect(TASK_PROVIDERS.every((p) => p.category === 'ai' && p.chat)).toBe(true);
  });

  it('BRAIN_CHAT_PROVIDERS holds exactly the chat-capable provider ids', () => {
    const expected = new Set(PROVIDERS.filter((p) => p.chat).map((p) => p.id));
    expect(BRAIN_CHAT_PROVIDERS).toEqual(expected);
  });
});

describe('groupProviders', () => {
  const buckets = groupProviders(AI_PROVIDERS);

  it('assigns every item to a bucket matching its own group', () => {
    for (const bucket of buckets) {
      for (const item of bucket.items) {
        expect(item.group).toBe(bucket.group);
      }
    }
  });

  it('loses no providers', () => {
    const flat = buckets.flatMap((b) => b.items);
    expect(flat).toHaveLength(AI_PROVIDERS.length);
    expect(new Set(flat.map((p) => p.id))).toEqual(
      new Set(AI_PROVIDERS.map((p) => p.id)),
    );
  });

  it('orders groups by first appearance in the catalog', () => {
    const firstSeen: string[] = [];
    for (const p of AI_PROVIDERS) {
      if (!firstSeen.includes(p.group)) firstSeen.push(p.group);
    }
    expect(buckets.map((b) => b.group)).toEqual(firstSeen);
  });

  it('keeps catalog order within each group', () => {
    for (const bucket of buckets) {
      const expected = AI_PROVIDERS.filter((p) => p.group === bucket.group);
      expect(bucket.items).toEqual(expected);
    }
  });

  it('labels every bucket', () => {
    for (const bucket of buckets) {
      expect(typeof bucket.label).toBe('string');
      expect(bucket.label.length).toBeGreaterThan(0);
    }
  });
});
