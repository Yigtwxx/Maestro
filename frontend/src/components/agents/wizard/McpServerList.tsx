'use client';

import { useCallback, useEffect, useState } from 'react';
import { Plus, RefreshCw, Server, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Modal } from '@/components/ui/Modal';
import { McpServerForm } from '@/components/agents/wizard/McpServerForm';
import { api, ApiError } from '@/lib/api';
import { cn } from '@/lib/cn';
import type { McpDiscoverResult, McpServer } from '@/types';

interface McpServerListProps {
  /** Ids this agent has attached. */
  selected: string[];
  onChange: (ids: string[]) => void;
  max: number;
}

export function McpServerList({ selected, onChange, max }: McpServerListProps) {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<McpServer | undefined>();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const [discovered, setDiscovered] = useState<
    Record<string, McpDiscoverResult | 'running'>
  >({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setServers(await api.listMcpServers());
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'MCP servers could not be loaded.',
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

  const runDiscovery = async (server: McpServer) => {
    setDiscovered((prev) => ({ ...prev, [server.id]: 'running' }));
    try {
      const result = await api.discoverMcpServer(server.id);
      setDiscovered((prev) => ({ ...prev, [server.id]: result }));
      await load();
    } catch (err) {
      setDiscovered((prev) => ({
        ...prev,
        [server.id]: {
          ok: false,
          server_name: '',
          server_version: '',
          protocol_version: '',
          tools: [],
          withheld: 0,
          duration_ms: 0,
          error: err instanceof Error ? err.message : 'Discovery failed.',
        },
      }));
    }
  };

  const remove = async (server: McpServer) => {
    setError(undefined);
    try {
      await api.deleteMcpServer(server.id);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `${server.name} could not be deleted.`,
      );
      return;
    }
    onChange(selected.filter((entry) => entry !== server.id));
    await load();
  };

  const atLimit = selected.length >= max;

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-micro text-module-agents">[ MCP SERVERS ]</p>
          <p className="mt-1 text-xs text-muted/80">
            Connect a remote Model Context Protocol server and its tools become
            the agent&apos;s. Up to {max} per agent.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          module="agents"
          onClick={() => setCreating(true)}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add server
        </Button>
      </div>

      {error && <p className="mb-3 text-sm text-danger">&gt; ERROR: {error}</p>}

      {loading ? (
        <p className="text-xs text-muted">Loading your servers…</p>
      ) : servers.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-2/30 px-4 py-8 text-center">
          <Server className="h-5 w-5 text-muted" aria-hidden />
          <p className="max-w-sm text-xs text-muted">
            No MCP servers connected. Add one to give this agent a whole toolset
            Maestro does not ship itself.
          </p>
        </div>
      ) : (
        <ul className="grid gap-3">
          {servers.map((server) => {
            const checked = selected.includes(server.id);
            const usable = server.tools.filter((tool) => !tool.blocked_reason);
            const blocked = server.tools.filter((tool) => tool.blocked_reason);
            const result = discovered[server.id];
            return (
              <li
                key={server.id}
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
                  onChange={(e) => toggle(server.id, e.target.checked)}
                  label={
                    <span className="flex flex-wrap items-baseline gap-2">
                      {server.name}
                      <code className="text-xs text-muted">
                        {usable.length} tool{usable.length === 1 ? '' : 's'}
                      </code>
                    </span>
                  }
                  hint={server.description || undefined}
                />

                <div className="mt-2 flex flex-wrap items-center gap-2 pl-[26px]">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => void runDiscovery(server)}
                    loading={result === 'running'}
                  >
                    <RefreshCw className="h-3.5 w-3.5" aria-hidden />
                    {server.tools.length === 0
                      ? 'Discover tools'
                      : 'Rediscover'}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setEditing(server)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => void remove(server)}
                  >
                    Delete
                  </Button>
                  {server.secret_hint && (
                    <span className="text-xs text-muted/70">
                      key {server.secret_hint}
                    </span>
                  )}
                  {server.tools_stale && server.tools.length > 0 && (
                    <span className="text-xs text-warning">
                      catalog may be out of date
                    </span>
                  )}
                </div>

                {usable.length > 0 && (
                  <ul className="mt-2 grid gap-1 pl-[26px]">
                    {usable.map((tool) => (
                      <li key={tool.action} className="text-xs text-muted">
                        <code className="text-white">{tool.display_name}</code>
                        {tool.description ? ` — ${tool.description}` : ''}
                      </li>
                    ))}
                  </ul>
                )}

                {blocked.length > 0 && (
                  <div className="mt-2 pl-[26px]">
                    <p className="flex items-start gap-1.5 text-xs text-warning">
                      <ShieldAlert
                        className="mt-0.5 h-3.5 w-3.5 shrink-0"
                        aria-hidden
                      />
                      {blocked.length} tool{blocked.length === 1 ? '' : 's'}{' '}
                      withheld — Maestro will not put{' '}
                      {blocked.length === 1 ? 'it' : 'them'} in an agent&apos;s
                      instructions.
                    </p>
                    <ul className="mt-1 grid gap-0.5">
                      {blocked.map((tool) => (
                        <li
                          key={tool.remote_name}
                          className="text-xs text-muted/70"
                        >
                          <code>{tool.remote_name}</code>: {tool.blocked_reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {result && result !== 'running' && !result.ok && (
                  <p className="mt-2 pl-[26px] text-xs text-warning">
                    {result.error}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {atLimit && (
        <p className="mt-2 text-xs text-warning">
          {max} servers attached — the cap keeps the agent&apos;s instructions
          from filling up with tool schemas. Unselect one to swap.
        </p>
      )}

      <Modal
        open={creating || Boolean(editing)}
        onClose={() => {
          setCreating(false);
          setEditing(undefined);
        }}
        label={editing ? 'Edit MCP server' : 'Connect an MCP server'}
        className="max-w-2xl"
      >
        <McpServerForm
          initial={editing}
          onCancel={() => {
            setCreating(false);
            setEditing(undefined);
          }}
          onSubmit={async (input) => {
            if (editing) {
              await api.updateMcpServer(editing.id, input);
            } else {
              const created = await api.createMcpServer(input);
              if (selected.length < max) onChange([...selected, created.id]);
              // A freshly registered server has an empty catalog until someone
              // asks; do it once here so the user sees tools immediately.
              void runDiscovery(created);
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
