'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { AdminReport, ReportStatus } from '@/types';

const FILTERS: { value: ReportStatus | 'all'; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'all', label: 'All' },
];

export default function AdminReportsPage() {
  const [filter, setFilter] = useState<ReportStatus | 'all'>('open');
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReports(await api.adminListReports(filter === 'all' ? undefined : filter));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Reports could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const resolve = async (id: string, resolution: ReportStatus) => {
    setBusy(id);
    try {
      await api.adminResolveReport(id, resolution);
      toast.success(`Report ${resolution}.`);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Action failed.');
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            onClick={() => setFilter(f.value)}
            className={`rounded-md border px-3 py-1 text-sm transition-colors ${
              filter === f.value
                ? 'border-module-admin bg-module-admin/10 text-module-admin'
                : 'border-border text-muted hover:text-white'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <SkeletonList module="admin" rows={3} />
      ) : reports.length === 0 ? (
        <p className="text-sm text-muted">&gt; No reports in this view.</p>
      ) : (
        <ul className="space-y-2">
          {reports.map((r) => (
            <li key={r.id} className="rounded-md border border-border bg-surface p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge module="admin" className="uppercase">
                  {r.target_type}
                </Badge>
                <Badge tone="danger" className="uppercase">
                  {r.reason}
                </Badge>
                <Badge tone={r.status === 'open' ? 'gray' : 'cyan'}>{r.status}</Badge>
              </div>
              <p className="font-mono text-xs text-muted">target: {r.target_id}</p>
              <p className="font-mono text-xs text-muted">
                reporter: {r.reporter_id.slice(0, 8)}
              </p>
              {r.note && <p className="mt-2 text-sm text-white">“{r.note}”</p>}
              {r.status === 'open' && (
                <div className="mt-3 flex gap-2">
                  <Button
                    variant="outline"
                    module="admin"
                    loading={busy === r.id}
                    onClick={() => void resolve(r.id, 'resolved')}
                  >
                    Resolve
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={busy === r.id}
                    onClick={() => void resolve(r.id, 'dismissed')}
                  >
                    Dismiss
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
