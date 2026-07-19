'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import type { AdminAuditEntry } from '@/types';

function when(iso: string | null): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function AdminAuditPage() {
  const [entries, setEntries] = useState<AdminAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setEntries(await api.adminListAudit());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Audit could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <SkeletonList module="admin" rows={4} />;
  if (error) return <p className="text-sm text-danger">&gt; ERROR: {error}</p>;
  if (entries.length === 0) return <p className="text-sm text-muted">&gt; No actions logged yet.</p>;

  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <li key={e.id} className="rounded-md border border-border bg-surface p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge module="admin" className="uppercase">
              {e.action}
            </Badge>
            <span className="font-mono text-xs text-muted">
              {e.target_type}:{e.target_id.slice(0, 12)}
            </span>
            <span className="ml-auto text-xs text-muted">{when(e.created_at)}</span>
          </div>
          <p className="mt-1 font-mono text-xs text-muted">
            by {e.actor_id.slice(0, 8)}
            {e.reason ? ` · ${e.reason}` : ''}
          </p>
        </li>
      ))}
    </ul>
  );
}
