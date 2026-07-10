'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { AgentForm } from '@/components/agents/AgentForm';
import { api, ApiError } from '@/lib/api';
import type { AgentConfig, ToolCatalogItem } from '@/types';

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
      <p className="px-6 py-8 font-mono text-sm text-module-agents">
        &gt; LOADING<span className="animate-blink">_</span>
      </p>
    );
  }

  if (error || !agent) {
    return (
      <p className="px-6 py-8 text-sm text-danger">
        &gt; ERROR: {error ?? 'Agent not found.'}
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 pt-5 pb-8">
      <AgentForm
        tools={tools}
        initial={{
          name: agent.name,
          domain: agent.domain,
          system_prompt: agent.system_prompt,
          tools: agent.tools,
        }}
        submitLabel="Save changes"
        onSubmit={async (input) => {
          await api.updateAgent(agent.id, input);
          router.push('/agents');
        }}
      />
    </div>
  );
}
