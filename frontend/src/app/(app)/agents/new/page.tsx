'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { AgentWizard } from '@/components/agents/wizard/AgentWizard';
import { PageShell } from '@/components/layout/PageShell';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { ToolCatalogItem } from '@/types';

const mc = MODULE_COLOR.agents;

export default function NewAgentPage() {
  const router = useRouter();
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTools(await api.listTools());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Tool catalog could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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
        <p className={`mt-4 text-micro ${mc.text}`}>[ NEW AGENT ]</p>
        <h1 className="mt-1.5 text-xl font-bold text-white">Build an agent</h1>
        <p className="mt-1 max-w-xl text-sm text-muted">
          Give it an identity, tell it how to behave, pick what it can reach, and
          decide whether the orchestrator may route to it.
        </p>
      </div>

      {error && <p className="mb-4 text-sm text-danger">&gt; ERROR: {error}</p>}

      {loading ? (
        <SkeletonList module="agents" rows={3} />
      ) : (
        <AgentWizard
          tools={tools}
          submitLabel="Create agent"
          onSubmit={async (input) => {
            await api.createAgent(input);
            router.push('/agents');
          }}
        />
      )}
    </PageShell>
  );
}
