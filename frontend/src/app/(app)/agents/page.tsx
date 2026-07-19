'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Bot } from 'lucide-react';
import { AgentForm } from '@/components/agents/AgentForm';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card } from '@/components/ui/Card';
import { StatBlock } from '@/components/ui/StatBlock';
import { SkeletonList } from '@/components/ui/Skeleton';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { PageShell } from '@/components/layout/PageShell';
import { api, ApiError } from '@/lib/api';
import { localizeBuiltinAgent } from '@/lib/agent-locale';
import { domainColor } from '@/lib/agent-colors';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { AgentConfig, BuiltinAgent, ToolCatalogItem } from '@/types';

const mc = MODULE_COLOR.agents;

export default function AgentsPage() {
  const [builtin, setBuiltin] = useState<BuiltinAgent[]>([]);
  const [custom, setCustom] = useState<AgentConfig[]>([]);
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
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

  return (
    <PageShell>
      <div className="mb-4 flex items-center justify-between">
        <p className={`text-micro ${mc.text}`}>[ AGENT REGISTRY ]</p>
        <Button
          variant={creating ? 'ghost' : 'solid'}
          module={creating ? undefined : 'agents'}
          onClick={() => setCreating((v) => !v)}
        >
          {creating ? 'Close' : '+ New Agent'}
        </Button>
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

      <section className="mb-8">
        <p className={`text-micro mb-3 ${mc.text}`}>[ BUILT-IN DOMAIN AGENTS ]</p>
        <div className="flex flex-wrap gap-2">
          {builtin.map((agent) => (
            <Badge key={agent.id} domain={agent.domain} className="capitalize">
              {agent.name}
            </Badge>
          ))}
        </div>
      </section>

      <section>
        <p className={`text-micro mb-3 ${mc.text}`}>[ CUSTOM AGENTS ]</p>
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
          <p className="text-sm text-muted">
            &gt; No custom agents yet. Create one with &quot;New Agent&quot;.
          </p>
        ) : (
          <Stagger className="grid gap-4 sm:grid-cols-2">
            {custom.map((agent) => (
              <StaggerItem key={agent.id}>
                <Card glow domain={agent.domain} className="p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <Bot
                      className={`h-4 w-4 ${domainColor(agent.domain).text}`}
                      aria-hidden
                    />
                    <p className="flex-1 truncate font-bold text-white">{agent.name}</p>
                  </div>
                  <div className="mb-4 grid grid-cols-2 gap-3 rounded-md border border-border bg-surface-2 p-3">
                    <StatBlock
                      size="sm"
                      label="Domain"
                      value={<span className="capitalize">{agent.domain}</span>}
                    />
                    <StatBlock size="sm" label="Tools" value={agent.tools.length} />
                  </div>
                  <div className="flex justify-end gap-2">
                    <Link href={`/agents/${agent.id}`}>
                      <Button variant="cyan-outline">Edit</Button>
                    </Link>
                    <Button variant="danger-outline" onClick={() => onDelete(agent.id)}>
                      Delete
                    </Button>
                  </div>
                </Card>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </section>
    </PageShell>
  );
}
