'use client';

import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import { cn } from '@/lib/cn';
import type {
  CustomApiAuthMode,
  CustomApiMethod,
  CustomApiParameter,
  CustomApiParameterType,
  CustomApiTool,
  CustomApiToolInput,
} from '@/types';

interface CustomApiToolFormProps {
  initial?: CustomApiTool;
  onSubmit: (input: CustomApiToolInput) => Promise<void>;
  onCancel: () => void;
}

const METHODS: { value: CustomApiMethod; label: string }[] = [
  { value: 'GET', label: 'GET' },
  { value: 'POST', label: 'POST' },
];

const AUTH_MODES: { value: CustomApiAuthMode; label: string }[] = [
  { value: 'none', label: 'No credential' },
  { value: 'bearer', label: 'Bearer token' },
  { value: 'header', label: 'Custom header' },
  { value: 'query', label: 'Query parameter' },
];

const PARAM_TYPES: { value: CustomApiParameterType; label: string }[] = [
  { value: 'string', label: 'string' },
  { value: 'integer', label: 'integer' },
  { value: 'number', label: 'number' },
  { value: 'boolean', label: 'boolean' },
];

function emptyParameter(): CustomApiParameter {
  return { name: '', type: 'string', description: '', required: false };
}

export function CustomApiToolForm({
  initial,
  onSubmit,
  onCancel,
}: CustomApiToolFormProps) {
  const editing = Boolean(initial);
  const [slug, setSlug] = useState(initial?.slug ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [method, setMethod] = useState<CustomApiMethod>(initial?.method ?? 'GET');
  const [baseUrl, setBaseUrl] = useState(initial?.base_url ?? 'https://');
  const [pathTemplate, setPathTemplate] = useState(initial?.path_template ?? '/');
  const [authMode, setAuthMode] = useState<CustomApiAuthMode>(
    initial?.auth_mode ?? 'none',
  );
  const [authName, setAuthName] = useState(initial?.auth_name ?? '');
  const [secret, setSecret] = useState('');
  const [parameters, setParameters] = useState<CustomApiParameter[]>(
    initial?.parameters ?? [],
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const patchParameter = (index: number, patch: Partial<CustomApiParameter>) => {
    setParameters((prev) =>
      prev.map((param, i) => (i === index ? { ...param, ...patch } : param)),
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
        method,
        base_url: baseUrl,
        path_template: pathTemplate,
        auth_mode: authMode,
        auth_name: authMode === 'bearer' ? '' : authName,
        // Omitted when blank on an edit: sending an empty string would rotate a
        // working credential away, which renaming a tool must never do.
        ...(secret ? { secret } : {}),
        parameters,
        enabled: initial?.enabled ?? true,
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
          label="Display name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="CRM Lookup"
          maxLength={60}
          required
          module="agents"
        />
        <Input
          label="Slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="crm_lookup"
          disabled={editing}
          pattern="[a-z][a-z0-9_]{1,30}"
          required
          module="agents"
        />
      </div>
      <p className="-mt-2 text-xs text-muted/70">
        The slug is how the agent names this tool in a call, so it cannot change
        after creation. Lower case, digits and underscores.
      </p>

      <Textarea
        label="What does it do?"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        maxLength={280}
        placeholder="Looks a customer up by id and returns their plan and status."
        module="agents"
      />
      <p className="-mt-2 text-xs text-muted/70">
        Shown to the model, so write it for the model. Scanned for injection
        patterns on save — it becomes part of the agent&apos;s instructions.
      </p>

      <div className="grid gap-4 sm:grid-cols-[8rem_1fr]">
        <Select
          label="Method"
          value={method}
          onChange={(e) => setMethod(e.target.value as CustomApiMethod)}
          options={METHODS}
          module="agents"
        />
        <Input
          label="Base URL"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.example.com"
          required
          module="agents"
        />
      </div>

      <div>
        <Input
          label="Path"
          value={pathTemplate}
          onChange={(e) => setPathTemplate(e.target.value)}
          placeholder="/v1/customers/{customer_id}"
          required
          module="agents"
        />
        <p className="mt-1.5 text-xs text-muted/70">
          Use <code className="text-white">{'{name}'}</code> to drop a parameter
          in. Values are URL-encoded, so a parameter can never add a path segment
          or a query of its own.
        </p>
      </div>

      <fieldset className="grid gap-3 rounded-md border border-border p-3">
        <legend className="px-1 text-micro text-muted">Authentication</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Mode"
            value={authMode}
            onChange={(e) => setAuthMode(e.target.value as CustomApiAuthMode)}
            options={AUTH_MODES}
            module="agents"
          />
          {authMode === 'header' || authMode === 'query' ? (
            <Input
              label={authMode === 'header' ? 'Header name' : 'Parameter name'}
              value={authName}
              onChange={(e) => setAuthName(e.target.value)}
              placeholder={authMode === 'header' ? 'X-Api-Key' : 'api_key'}
              required
              module="agents"
            />
          ) : null}
        </div>
        {authMode !== 'none' && (
          <div>
            <Input
              label="Secret"
              type="password"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={
                initial?.secret_hint
                  ? `Stored (${initial.secret_hint}) — leave blank to keep it`
                  : 'Pasted once, encrypted at rest'
              }
              // Required whenever no credential is stored, not merely on
              // create: switching an existing tool from 'none' to a
              // credentialed mode has nothing to keep, and a blank field would
              // omit `secret` from the payload and save an authenticated mode
              // with no key — failing only later, at call time.
              required={!initial?.secret_hint}
              module="agents"
            />
            <p className="mt-1.5 text-xs text-muted/70">
              Encrypted with AES-256-GCM and never returned to this page again —
              only the masked tail.
            </p>
          </div>
        )}
      </fieldset>

      <fieldset className="grid gap-3 rounded-md border border-border p-3">
        <legend className="px-1 text-micro text-muted">
          Parameters the agent may fill
        </legend>
        {parameters.length === 0 && (
          <p className="text-xs text-muted/70">
            None yet. Without parameters the agent calls a fixed URL, which is
            fine for an endpoint that takes no input.
          </p>
        )}
        {parameters.map((param, index) => (
          <div
            key={index}
            className="grid gap-2 rounded border border-border/60 bg-surface-2/40 p-2 sm:grid-cols-[1fr_7rem_auto]"
          >
            <Input
              aria-label="Parameter name"
              value={param.name}
              onChange={(e) => patchParameter(index, { name: e.target.value })}
              placeholder="customer_id"
              module="agents"
            />
            <Select
              aria-label="Parameter type"
              value={param.type}
              onChange={(e) =>
                patchParameter(index, {
                  type: e.target.value as CustomApiParameterType,
                })
              }
              options={PARAM_TYPES}
              module="agents"
            />
            <button
              type="button"
              onClick={() =>
                setParameters((prev) => prev.filter((_, i) => i !== index))
              }
              aria-label={`Remove parameter ${param.name || index + 1}`}
              className={cn(
                'self-center rounded p-2 text-muted transition-colors',
                'hover:bg-danger-dim hover:text-danger focus-visible:outline-none',
                'focus-visible:ring-1 focus-visible:ring-danger',
              )}
            >
              <Trash2 className="h-4 w-4" aria-hidden />
            </button>
            <div className="sm:col-span-3">
              <Input
                aria-label="Parameter description"
                value={param.description}
                onChange={(e) =>
                  patchParameter(index, { description: e.target.value })
                }
                placeholder="What this value is, in the model's terms"
                maxLength={200}
                module="agents"
              />
            </div>
            <div className="sm:col-span-3">
              <Checkbox
                module="agents"
                checked={param.required}
                onChange={(e) =>
                  patchParameter(index, { required: e.target.checked })
                }
                label="Required"
                hint="The agent is told it must supply this before calling."
              />
            </div>
          </div>
        ))}
        <div>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setParameters((prev) => [...prev, emptyParameter()])}
          >
            <Plus className="h-3.5 w-3.5" aria-hidden />
            Add parameter
          </Button>
        </div>
      </fieldset>

      {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button type="submit" variant="solid" module="agents" loading={saving}>
          {editing ? 'Save changes' : 'Register endpoint'}
        </Button>
      </div>
    </form>
  );
}
