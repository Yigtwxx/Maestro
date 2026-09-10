'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { SKILL_LIMITS } from '@/lib/constants';
import type { Skill, SkillInput, ToolCatalogItem } from '@/types';

interface SkillFormProps {
  initial?: Skill;
  /** The catalog, so a requirement is picked rather than typed. */
  tools: ToolCatalogItem[];
  onSubmit: (input: SkillInput) => Promise<void>;
  onCancel: () => void;
}

export function SkillForm({
  initial,
  tools,
  onSubmit,
  onCancel,
}: SkillFormProps) {
  const editing = Boolean(initial);
  const [slug, setSlug] = useState(initial?.slug ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [instructions, setInstructions] = useState(initial?.instructions ?? '');
  const [outputFormat, setOutputFormat] = useState(
    initial?.output_format ?? '',
  );
  const [requiredTools, setRequiredTools] = useState<string[]>(
    initial?.required_tools ?? [],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const toggleTool = (id: string, on: boolean) => {
    setRequiredTools((prev) =>
      on ? [...prev, id] : prev.filter((entry) => entry !== id),
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      await onSubmit({
        slug,
        name,
        description,
        instructions,
        output_format: outputFormat,
        required_tools: requiredTools,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Competitive teardown"
          maxLength={SKILL_LIMITS.name}
          required
          module="agents"
        />
        <Input
          label="Slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="competitive-teardown"
          disabled={editing}
          pattern="[a-z][a-z0-9_-]{1,40}"
          required
          module="agents"
        />
      </div>
      <p className="-mt-2 text-xs text-muted/70">
        The slug is the stable handle a plugin uses to upgrade this skill later,
        so it cannot change after creation.
      </p>

      <Textarea
        label="What is it for?"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        maxLength={SKILL_LIMITS.description}
        placeholder="How to pull a competitor's positioning apart."
        module="agents"
      />

      <div>
        <Textarea
          label="Instructions"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          rows={10}
          maxLength={SKILL_LIMITS.instructions}
          placeholder={
            'Start from their pricing page, then their changelog.\n' +
            'Name the one number that decides the question before anything else.'
          }
          required
          module="agents"
        />
        <p className="mt-1.5 text-xs text-muted/70">
          This text is added to the agent&apos;s instructions inside a sandboxed
          block, and it is scanned for injection patterns on save. It shapes{' '}
          <em>how</em> the agent works — it cannot grant tools, raise budgets or
          change the output contract.
        </p>
        <p className="mt-1 text-xs text-muted/70">
          {instructions.length}/{SKILL_LIMITS.instructions} characters.
        </p>
      </div>

      <Textarea
        label="Output shape (optional)"
        value={outputFormat}
        onChange={(e) => setOutputFormat(e.target.value)}
        rows={3}
        maxLength={SKILL_LIMITS.outputFormat}
        placeholder="A table of the five claims, then three bullets on what to do."
        module="agents"
      />

      <fieldset className="grid gap-2">
        <legend className="text-micro text-module-agents">
          [ TOOLS THIS SKILL EXPECTS ]
        </legend>
        <p className="text-xs text-muted/70">
          Advisory only. Attaching this skill never turns a tool on — an agent
          that is missing one is flagged in the wizard so you can enable it
          yourself.
        </p>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {tools
            .filter((tool) => tool.kind === 'executable')
            .map((tool) => (
              <Checkbox
                key={tool.id}
                module="agents"
                checked={requiredTools.includes(tool.id)}
                onChange={(e) => toggleTool(tool.id, e.target.checked)}
                label={tool.label}
              />
            ))}
        </div>
      </fieldset>

      {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </Button>
        <Button type="submit" variant="solid" module="agents" loading={saving}>
          {editing ? 'Save changes' : 'Create skill'}
        </Button>
      </div>
    </form>
  );
}
