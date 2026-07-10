'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { cn } from '@/lib/cn';
import { AGENT_DOMAINS } from '@/lib/constants';
import type { AgentConfigInput, ToolCatalogItem } from '@/types';

interface AgentFormProps {
  tools: ToolCatalogItem[];
  initial?: AgentConfigInput;
  submitLabel: string;
  onSubmit: (input: AgentConfigInput) => Promise<void>;
}

export function AgentForm({ tools, initial, submitLabel, onSubmit }: AgentFormProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [domain, setDomain] = useState(initial?.domain ?? 'general');
  const [systemPrompt, setSystemPrompt] = useState(initial?.system_prompt ?? '');
  const [selected, setSelected] = useState<string[]>(initial?.tools ?? []);
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);

  const toggleTool = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      await onSubmit({
        name,
        domain,
        system_prompt: systemPrompt,
        tools: selected,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="grid gap-4 rounded-lg border border-module-agents/30 bg-surface p-5"
    >
      <p className="text-micro text-module-agents">[ AGENT CONFIGURATION ]</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Agent Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="E.g. Finance Analyst"
          required
          module="agents"
        />
        <Select
          label="Domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          options={AGENT_DOMAINS.map((d) => ({ value: d, label: d }))}
          module="agents"
        />
      </div>

      <div>
        <Textarea
          label="System Prompt"
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={6}
          required
          placeholder="Describe the agent's behavior…"
          module="agents"
        />
        <p className="mt-1.5 text-xs text-muted/70">
          The system prompt is security-scanned for malicious patterns on save.
        </p>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-micro mb-2 text-muted">Tools</legend>
        <div className="flex flex-wrap gap-2">
          {tools.map((tool) => {
            const active = selected.includes(tool.id);
            return (
              <button
                key={tool.id}
                type="button"
                aria-pressed={active}
                onClick={() => toggleTool(tool.id)}
                className={cn(
                  'rounded border px-3 py-1.5 text-xs font-medium transition-colors',
                  active
                    ? 'border-module-agents bg-module-agents text-black'
                    : 'border-border bg-surface-2 text-muted hover:border-border-bright hover:text-white',
                )}
              >
                {tool.label}
              </button>
            );
          })}
        </div>
      </fieldset>

      {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}
      <div>
        <Button type="submit" variant="solid" module="agents" loading={saving}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
