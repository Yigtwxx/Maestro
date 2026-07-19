'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { PageShell } from '@/components/layout/PageShell';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { TraceWaterfall } from '@/components/trace/TraceWaterfall';
import { TraceSummaryPanel } from '@/components/trace/TraceSummaryPanel';
import { SpanDetail } from '@/components/trace/SpanDetail';
import { TraceEmptyState } from '@/components/trace/TraceEmptyState';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { TaskSummary, TaskTrace, TraceSummary } from '@/types';

const mc = MODULE_COLOR.traces;

function TracesView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const taskParam = searchParams.get('task') ?? '';

  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [selectedId, setSelectedId] = useState(taskParam);
  const [trace, setTrace] = useState<TaskTrace | undefined>();
  const [summary, setSummary] = useState<TraceSummary | undefined>();
  const [selectedSpanId, setSelectedSpanId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  // Populate the picker from recent tasks (best-effort; failure just leaves it
  // empty and deep-linked traces still load).
  useEffect(() => {
    api
      .listTasks()
      .then((res) => setTasks(res.items))
      .catch(() => undefined);
  }, []);

  // A deep link (e.g. the architect "View trace" link) drives the selection.
  useEffect(() => {
    if (taskParam) setSelectedId(taskParam);
  }, [taskParam]);

  const loadTrace = useCallback(async (taskId: string) => {
    setLoading(true);
    setError(undefined);
    setSelectedSpanId(undefined);
    try {
      const [t, s] = await Promise.all([
        api.getTaskTrace(taskId),
        api.getTaskTraceSummary(taskId),
      ]);
      setTrace(t);
      setSummary(s);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Trace could not be loaded.');
      setTrace(undefined);
      setSummary(undefined);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) {
      void loadTrace(selectedId);
    } else {
      setTrace(undefined);
      setSummary(undefined);
    }
  }, [selectedId, loadTrace]);

  const onPick = (id: string) => {
    setSelectedId(id);
    router.replace(id ? `/traces?task=${id}` : '/traces');
  };

  const selectedSpan = useMemo(
    () => trace?.spans.find((sp) => sp.span_id === selectedSpanId),
    [trace, selectedSpanId],
  );

  const options = useMemo(() => {
    const rows = tasks.map((t) => ({
      value: t.task_id,
      label: `${t.task_id.slice(0, 8)} · ${t.status} · ${t.prompt.slice(0, 44)}`,
    }));
    // Surface a deep-linked task that isn't in the recent list.
    if (selectedId && !tasks.some((t) => t.task_id === selectedId)) {
      rows.unshift({ value: selectedId, label: `${selectedId.slice(0, 8)} · (linked)` });
    }
    return [{ value: '', label: 'Select a task…' }, ...rows];
  }, [tasks, selectedId]);

  const hasSpans = trace !== undefined && trace.spans.length > 0;

  return (
    <PageShell>
      <header className="mb-6">
        <p className={`text-micro mb-1 ${mc.text}`}>[ TRACES ]</p>
        <h1 className="text-2xl font-bold text-white">Execution traces</h1>
        <p className="mt-1 text-sm text-muted">
          Span waterfall, token usage and cost for a task&apos;s agent hierarchy.
        </p>
      </header>

      <div className="mb-6 max-w-xl">
        <Select
          module="traces"
          label="Task"
          value={selectedId}
          onChange={(e) => onPick(e.target.value)}
          options={options}
        />
      </div>

      {!selectedId && (
        <Card className="text-center">
          <p className="text-sm text-muted">&gt; Select a task to view its trace.</p>
        </Card>
      )}

      {selectedId && loading && (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <SkeletonCard module="traces" lines={1} />
            <SkeletonCard module="traces" lines={1} />
            <SkeletonCard module="traces" lines={1} />
          </div>
          <SkeletonCard module="traces" lines={6} />
        </div>
      )}

      {selectedId && !loading && error && (
        <p className="text-sm text-danger">&gt; ERROR: {error}</p>
      )}

      {selectedId && !loading && !error && trace && !hasSpans && <TraceEmptyState />}

      {selectedId && !loading && !error && hasSpans && summary && (
        <div className="space-y-6">
          <TraceSummaryPanel summary={summary} />
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <TraceWaterfall
                spans={trace.spans}
                selectedSpanId={selectedSpanId}
                onSelectSpan={setSelectedSpanId}
              />
            </div>
            <div className="lg:col-span-1">
              <SpanDetail span={selectedSpan} />
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}

export default function TracesPage() {
  return (
    <Suspense fallback={null}>
      <TracesView />
    </Suspense>
  );
}
