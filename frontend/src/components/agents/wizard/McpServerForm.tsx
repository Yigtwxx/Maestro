'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Textarea } from '@/components/ui/Textarea';
import type { McpAuthMode, McpServer, McpServerInput } from '@/types';

interface McpServerFormProps {
  initial?: McpServer;
  onSubmit: (input: McpServerInput) => Promise<void>;
  onCancel: () => void;
}

const AUTH_MODES: { value: McpAuthMode; label: string }[] = [
  { value: 'none', label: 'No credential' },
  { value: 'bearer', label: 'Bearer token' },
  { value: 'header', label: 'Custom header' },
];

export function McpServerForm({
  initial,
  onSubmit,
  onCancel,
}: McpServerFormProps) {
  const editing = Boolean(initial);
  const [slug, setSlug] = useState(initial?.slug ?? '');
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [url, setUrl] = useState(initial?.url ?? 'https://');
  const [authMode, setAuthMode] = useState<McpAuthMode>(
    initial?.auth_mode ?? 'none',
  );
  const [authName, setAuthName] = useState(initial?.auth_name ?? '');
  const [secret, setSecret] = useState('');
  const [timeout, setTimeout] = useState(initial?.timeout_seconds ?? 30);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(undefined);
    setSaving(true);
    try {
      await onSubmit({
        slug,
        name,
        description,
        url,
        transport: 'streamable_http',
        headers: initial?.headers ?? {},
        auth_mode: authMode,
        auth_name: authMode === 'bearer' ? '' : authName,
        // Omitted when blank on an edit: sending an empty string would rotate a
        // working credential away, which renaming a server must never do.
        ...(secret ? { secret } : {}),
        timeout_seconds: timeout,
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
          placeholder="Acme Tools"
          maxLength={60}
          required
          module="agents"
        />
        <Input
          label="Slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="acme"
          disabled={editing}
          pattern="[a-z][a-z0-9_]{1,16}"
          required
          module="agents"
        />
      </div>
      <p className="-mt-2 text-xs text-muted/70">
        The slug sits inside every action id this server&apos;s tools produce,
        so it cannot change after creation. Lower case, digits and underscores.
      </p>

      <div>
        <Input
          label="Server URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://mcp.example.com/mcp"
          required
          module="agents"
        />
        <p className="mt-1.5 text-xs text-muted/70">
          A remote Streamable HTTP endpoint. Local <code>stdio</code> servers
          are not supported — Maestro runs your agents on its own machines, so a
          local server would be one of ours, not one of yours.
        </p>
      </div>

      <Textarea
        label="What is it for? (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        maxLength={280}
        placeholder="Acme's internal search and ticketing tools."
        module="agents"
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <Select
          label="Authentication"
          value={authMode}
          onChange={(e) => setAuthMode(e.target.value as McpAuthMode)}
          options={AUTH_MODES}
          module="agents"
        />
        {authMode === 'header' && (
          <Input
            label="Header name"
            value={authName}
            onChange={(e) => setAuthName(e.target.value)}
            placeholder="X-API-Key"
            maxLength={80}
            required
            module="agents"
          />
        )}
      </div>

      {authMode !== 'none' && (
        <div>
          <Input
            label={editing ? 'Replace credential (optional)' : 'Credential'}
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={initial?.secret_hint ?? 'sk-…'}
            required={!editing}
            module="agents"
          />
          <p className="mt-1.5 text-xs text-muted/70">
            Encrypted at rest and never returned — you will only ever see the
            last four characters. Leave blank when editing to keep the stored
            one. OAuth servers are not supported yet; this has to be a static
            token the server accepts.
          </p>
        </div>
      )}

      <Input
        label="Timeout (seconds)"
        type="number"
        min={1}
        max={120}
        value={timeout}
        onChange={(e) => setTimeout(Number(e.target.value))}
        module="agents"
      />
      <p className="-mt-2 text-xs text-muted/70">
        A budget for one whole tool call, which is three requests to the server
        — not a limit per request.
      </p>

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
          {editing ? 'Save changes' : 'Register server'}
        </Button>
      </div>
    </form>
  );
}
