'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Search } from 'lucide-react';
import { AgentForm } from '@/components/agents/AgentForm';
import { BuiltinAgentCard } from '@/components/agents/BuiltinAgentCard';
import { CustomAgentCard } from '@/components/agents/CustomAgentCard';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { StatBlock } from '@/components/ui/StatBlock';
import { SkeletonList } from '@/components/ui/Skeleton';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { PageShell } from '@/components/layout/PageShell';
import { api, ApiError } from '@/lib/api';
import { localizeBuiltinAgent } from '@/lib/agent-locale';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { AgentConfig, BuiltinAgent, ToolCatalogItem } from '@/types';

const mc = MODULE_COLOR.agents;

/** Case-insensitive substring match across an agent's searchable text. */
function matches(query: string, ...fields: string[]): boolean {
  if (!query) return true;
  const needle = query.toLowerCase();
  return fields.some((field) => field.toLowerCase().includes(needle));
}

export default function AgentsPage() {
  const [builtin, setBuiltin] = useState<BuiltinAgent[]>([]);
  const [custom, setCustom] = useState<AgentConfig[]>([]);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, toolList] = await Promise.all([api.listAgents(), api.listTools()]);
      setBuiltin(list.builtin.map(localizeBuiltinAgent));
      setCustom(list.custom);
      setTools(toolList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Agent list could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onDelete = async (id: string) => {
    await api.deleteAgent(id);
    await load();
  };

  const toolLabels = useMemo(
    () => Object.fromEntries(tools.map((tool) => [tool.id, tool.label])),
    [tools],
  );

  const filteredBuiltin = useMemo(
    () =>
      builtin.filter((agent) =>
        matches(query, agent.name, agent.domain, agent.description, ...agent.capabilities),
      ),
    [builtin, query],
  );

  const filteredCustom = useMemo(
    () => custom.filter((agent) => matches(query, agent.name, agent.domain)),
    [custom, query],
  );

  return (
    <PageShell>
      {/* Hero: identity, live counts, and the primary create action. */}
      <div className="mb-6 flex flex-col gap-5 rounded-lg border border-border bg-surface p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className={`text-micro ${mc.text}`}>[ AGENT REGISTRY ]</p>
          <h1 className="mt-1.5 text-xl font-bold text-white">Agents</h1>
          <p className="mt-1 max-w-xl text-sm text-muted">
            Built-in domain squads ship ready to run. Build your own agents with a
            custom prompt and a curated tool set.
          </p>
        </div>
        <Button
          variant={creating ? 'ghost' : 'solid'}
          module={creating ? undefined : 'agents'}
          onClick={() => setCreating((v) => !v)}
        >
          {creating ? 'Close' : '+ New Agent'}
        </Button>
      </div>

      <div className="mb-6 grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-border bg-surface p-4">
          <StatBlock label="Built-in squads" value={builtin.length} module="agents" />
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <StatBlock label="Custom agents" value={custom.length} module="agents" />
        </div>
        <div className="rounded-lg border border-border bg-surface p-4">
          <StatBlock label="Tools available" value={tools.length} module="agents" />
        </div>
      </div>

      {error && <p className="mb-4 text-sm text-danger">&gt; ERROR: {error}</p>}

      {creating && (
        <div className="mb-8">
          <AgentForm
            tools={tools}
            submitLabel="Create agent"
            onSubmit={async (input) => {
              await api.createAgent(input);
              setCreating(false);
              await load();
            }}
          />
        </div>
      )}

      <div className="mb-6">
        <div className="relative max-w-sm">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            aria-label="Search agents"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search agents…"
            module="agents"
            className="pl-9"
          />
        </div>
      </div>

      <section className="mb-10">
        <div className="mb-3 flex items-baseline gap-2">
          <p className={`text-micro ${mc.text}`}>[ BUILT-IN DOMAIN AGENTS ]</p>
          <span className="text-micro text-muted">{filteredBuiltin.length}</span>
        </div>
        {loading ? (
          <SkeletonList module="agents" rows={3} />
        ) : filteredBuiltin.length === 0 ? (
          <p className="text-sm text-muted">&gt; No squads match &quot;{query}&quot;.</p>
        ) : (
          <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredBuiltin.map((agent) => (
              <StaggerItem key={agent.id}>
                <BuiltinAgentCard agent={agent} />
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-baseline gap-2">
          <p className={`text-micro ${mc.text}`}>[ CUSTOM AGENTS ]</p>
          {!loading && <span className="text-micro text-muted">{filteredCustom.length}</span>}
        </div>
        {loading ? (
          <>
            <p className={`font-mono text-sm ${mc.text}`}>
              &gt; LOADING<span className="animate-blink">_</span>
            </p>
            <div className="mt-4">
              <SkeletonList module="agents" rows={2} />
            </div>
          </>
        ) : custom.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border bg-surface/50 px-6 py-12 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full border border-border bg-surface-2">
              <Bot className={`h-6 w-6 ${mc.text}`} aria-hidden />
            </span>
            <p className="text-sm text-muted">
              No custom agents yet. Create one with &quot;New Agent&quot; to tailor a
              prompt and tool set to your workflow.
            </p>
            {!creating && (
              <Button variant="solid" module="agents" onClick={() => setCreating(true)}>
                + New Agent
              </Button>
            )}
          </div>
        ) : filteredCustom.length === 0 ? (
          <p className="text-sm text-muted">&gt; No custom agents match &quot;{query}&quot;.</p>
        ) : (
          <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredCustom.map((agent) => (
              <StaggerItem key={agent.id}>
                <CustomAgentCard
                  agent={agent}
                  toolLabels={toolLabels}
                  onDelete={onDelete}
                />
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </section>
    </PageShell>
  );
}
