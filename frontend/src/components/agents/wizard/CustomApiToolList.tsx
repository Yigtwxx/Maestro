'use client';

import { useCallback, useEffect, useState } from 'react';
import { Plug, Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Modal } from '@/components/ui/Modal';
import { CustomApiToolForm } from '@/components/agents/wizard/CustomApiToolForm';
import { api, ApiError } from '@/lib/api';
import { cn } from '@/lib/cn';
import type { CustomApiTool, CustomApiToolTestResult } from '@/types';

interface CustomApiToolListProps {
  /** Ids this agent has attached. */
  selected: string[];
  onChange: (ids: string[]) => void;
  max: number;
}

export function CustomApiToolList({
  selected,
  onChange,
  max,
}: CustomApiToolListProps) {
  const [tools, setTools] = useState<CustomApiTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<CustomApiTool | undefined>();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [tested, setTested] = useState<
    Record<string, CustomApiToolTestResult | 'running'>
  >({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTools(await api.listCustomApiTools());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'API tools could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: string, on: boolean) => {
    if (on && selected.length >= max) return;
    onChange(on ? [...selected, id] : selected.filter((entry) => entry !== id));
  };

  const runTest = async (tool: CustomApiTool) => {
    setTested((prev) => ({ ...prev, [tool.id]: 'running' }));
    try {
      const args = Object.fromEntries(
        tool.parameters.map((param) => [param.name, '']),
      );
      const result = await api.testCustomApiTool(tool.id, args);
      setTested((prev) => ({ ...prev, [tool.id]: result }));
    } catch (err) {
      setTested((prev) => ({
        ...prev,
        [tool.id]: {
          ok: false,
          status: 0,
          duration_ms: 0,
          preview: '',
          error: err instanceof Error ? err.message : 'Test failed.',
        },
      }));
    }
  };

  const remove = async (tool: CustomApiTool) => {
    setError(undefined);
    try {
      await api.deleteCustomApiTool(tool.id);
    } catch (err) {
      // Matches load/runTest: a rejection here would otherwise surface as an
      // unhandled promise with nothing shown to the user.
      setError(
        err instanceof ApiError ? err.message : `${tool.name} could not be deleted.`,
      );
      return;
    }
    onChange(selected.filter((entry) => entry !== tool.id));
    await load();
  };

  const atLimit = selected.length >= max;

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-micro text-module-agents">[ YOUR OWN APIs ]</p>
          <p className="mt-1 text-xs text-muted/80">
            Register an HTTP endpoint and the agent can call it like any other
            tool. Up to {max} per agent.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          module="agents"
          onClick={() => setCreating(true)}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add API
        </Button>
      </div>

      {error && <p className="mb-3 text-sm text-danger">&gt; ERROR: {error}</p>}

      {loading ? (
        <p className="text-xs text-muted">Loading your APIs…</p>
      ) : tools.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-2/30 px-4 py-8 text-center">
          <Plug className="h-5 w-5 text-muted" aria-hidden />
          <p className="max-w-sm text-xs text-muted">
            No endpoints registered yet. Add one to let this agent reach a system
            Maestro does not integrate with out of the box.
          </p>
        </div>
      ) : (
        <ul className="grid gap-3">
          {tools.map((tool) => {
            const checked = selected.includes(tool.id);
            const result = tested[tool.id];
            return (
              <li
                key={tool.id}
                className={cn(
                  'rounded-md border p-3 transition-colors',
                  checked
                    ? 'border-module-agents/50 bg-module-agents/5'
                    : 'border-border bg-surface-2/50',
                )}
              >
                <Checkbox
                  module="agents"
                  checked={checked}
                  disabled={!checked && atLimit}
                  onChange={(e) => toggle(tool.id, e.target.checked)}
                  label={
                    <span className="flex flex-wrap items-baseline gap-2">
                      {tool.name}
                      <code className="text-xs text-muted">
                        {tool.method} {tool.base_url}
                        {tool.path_template}
                      </code>
                    </span>
                  }
                  hint={tool.description || undefined}
                />

                <div className="mt-2 flex flex-wrap items-center gap-2 pl-[26px]">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => void runTest(tool)}
                    loading={result === 'running'}
                  >
                    Test call
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setEditing(tool)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => void remove(tool)}
                  >
                    Delete
                  </Button>
                  {tool.secret_hint && (
                    <span className="text-xs text-muted/70">
                      key {tool.secret_hint}
                    </span>
                  )}
                </div>

                {result && result !== 'running' && (
                  <div className="mt-2 pl-[26px]">
                    <p
                      className={cn(
                        'text-xs',
                        result.ok ? 'text-success' : 'text-warning',
                      )}
                    >
                      {result.ok
                        ? `Responded in ${result.duration_ms}ms.`
                        : result.error}
                    </p>
                    {result.preview && (
                      <>
                        <p className="mt-1.5 text-micro text-muted">
                          [ RESPONSE PREVIEW — UNTRUSTED CONTENT ]
                        </p>
                        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded border border-border bg-surface-2 p-2 font-mono text-[11px] text-muted">
                          {result.preview}
                        </pre>
                      </>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {atLimit && (
        <p className="mt-2 text-xs text-warning">
          {max} APIs attached — the cap keeps the agent&apos;s instructions from
          filling up with tool schemas. Unselect one to swap.
        </p>
      )}

      <Modal
        open={creating || Boolean(editing)}
        onClose={() => {
          setCreating(false);
          setEditing(undefined);
        }}
        label={editing ? 'Edit API endpoint' : 'Register an API endpoint'}
        className="max-w-2xl"
      >
        <CustomApiToolForm
          initial={editing}
          onCancel={() => {
            setCreating(false);
            setEditing(undefined);
          }}
          onSubmit={async (input) => {
            if (editing) {
              await api.updateCustomApiTool(editing.id, input);
            } else {
              const created = await api.createCustomApiTool(input);
              if (selected.length < max) onChange([...selected, created.id]);
            }
            setCreating(false);
            setEditing(undefined);
            await load();
          }}
        />
      </Modal>
    </section>
  );
}
