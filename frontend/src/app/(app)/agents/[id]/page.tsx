'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { AgentWizard } from '@/components/agents/wizard/AgentWizard';
import { PageShell } from '@/components/layout/PageShell';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import { draftFromAgent } from '@/lib/agent-wizard';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { AgentConfig, ToolCatalogItem } from '@/types';

const mc = MODULE_COLOR.agents;

export default function AgentEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [agent, setAgent] = useState<AgentConfig | undefined>();
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, toolList] = await Promise.all([
        api.getAgent(params.id),
        api.listTools(),
      ]);
      setAgent(a);
      setTools(toolList);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Agent could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <PageShell>
        <SkeletonList module="agents" rows={3} />
      </PageShell>
    );
  }

  if (error || !agent) {
    return (
      <PageShell>
        <p className="text-sm text-danger">
          &gt; ERROR: {error ?? 'Agent not found.'}
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="mb-6">
        <Link
          href="/agents"
          className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-module-agents"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          Back to agents
        </Link>
        <p className={`mt-4 text-micro ${mc.text}`}>[ EDIT AGENT ]</p>
        <h1 className="mt-1.5 text-xl font-bold text-white">{agent.name}</h1>
      </div>

      {/* The whole draft is seeded, not a subset: the wizard submits every
          field, so an omitted one would be blanked on save. */}
      <AgentWizard
        tools={tools}
        initial={draftFromAgent(agent)}
        submitLabel="Save changes"
        onSubmit={async (input) => {
          await api.updateAgent(agent.id, input);
          router.push('/agents');
        }}
      />
    </PageShell>
  );
}
