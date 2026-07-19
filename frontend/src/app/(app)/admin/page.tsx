'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import type { AdminOverview } from '@/types';

function Stat({ label, value, alert }: { label: string; value: number; alert?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="text-micro text-muted">{label}</p>
      <p className={`mt-2 text-2xl font-bold ${alert && value > 0 ? 'text-module-admin' : 'text-white'}`}>
        {value.toLocaleString()}
      </p>
    </div>
  );
}

export default function AdminOverviewPage() {
  const [data, setData] = useState<AdminOverview | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setData(await api.adminOverview());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Overview could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <SkeletonList module="admin" rows={4} />;
  if (error) return <p className="text-sm text-danger">&gt; ERROR: {error}</p>;
  if (!data) return undefined;

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="OPEN REPORTS" value={data.open_reports} alert />
        <Stat label="SUSPENDED USERS" value={data.suspended_total} alert />
        <Stat label="TOTAL USERS" value={data.users_total} />
        <Stat label="ADMINS" value={data.admins_total} />
        <Stat label="MARKETPLACE ITEMS" value={data.items_total} />
        <Stat label="HIDDEN ITEMS" value={data.items_hidden} alert />
        <Stat label="REMOVED ITEMS" value={data.items_removed} alert />
        <Stat label="REVIEWS" value={data.reviews_total} />
      </section>

      <section>
        <h2 className="mb-3 text-micro text-module-admin">[ RECENT PUBLISHES ]</h2>
        {data.recent_items.length === 0 ? (
          <p className="text-sm text-muted">&gt; No marketplace items yet.</p>
        ) : (
          <ul className="space-y-2">
            {data.recent_items.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-white">{item.name}</p>
                  <p className="truncate font-mono text-xs text-muted">
                    {item.domain}
                    {item.author_id ? ` · author ${item.author_id.slice(0, 8)}` : ''}
                  </p>
                </div>
                <Badge tone={item.status === 'published' ? 'cyan' : 'danger'}>
                  {item.status}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
