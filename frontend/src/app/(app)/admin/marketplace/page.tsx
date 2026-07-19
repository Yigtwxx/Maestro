'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { AdminMarketplaceItem, AdminReview, MarketplaceStatus } from '@/types';

const FILTERS: { value: MarketplaceStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'published', label: 'Published' },
  { value: 'hidden', label: 'Hidden' },
  { value: 'removed', label: 'Removed' },
];

function ReviewList({ itemId }: { itemId: string }) {
  const [reviews, setReviews] = useState<AdminReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setReviews(await api.adminListItemReviews(itemId));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Reviews could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (r: AdminReview) => {
    setBusy(r.id);
    try {
      await api.adminHideReview(r.id, !r.hidden);
      toast.success(r.hidden ? 'Review restored.' : 'Review hidden.');
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Action failed.');
    } finally {
      setBusy(undefined);
    }
  };

  if (loading) return <p className="px-4 py-2 text-xs text-muted">&gt; Loading reviews…</p>;
  if (reviews.length === 0)
    return <p className="px-4 py-2 text-xs text-muted">&gt; No reviews.</p>;

  return (
    <ul className="space-y-2 border-t border-border px-4 py-3">
      {reviews.map((r) => (
        <li key={r.id} className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs text-white">
              {'★'.repeat(r.rating)}
              <span className="text-muted">{'☆'.repeat(5 - r.rating)}</span>
              {r.hidden && <span className="ml-2 text-module-admin">hidden</span>}
            </p>
            {r.comment && <p className="truncate text-xs text-muted">{r.comment}</p>}
          </div>
          <Button
            variant="ghost"
            disabled={busy === r.id}
            onClick={() => void toggle(r)}
          >
            {r.hidden ? 'Unhide' : 'Hide'}
          </Button>
        </li>
      ))}
    </ul>
  );
}

export default function AdminMarketplacePage() {
  const [filter, setFilter] = useState<MarketplaceStatus | 'all'>('all');
  const [items, setItems] = useState<AdminMarketplaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | undefined>();
  const [expanded, setExpanded] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.adminListItems(filter === 'all' ? undefined : filter));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Items could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const setStatus = async (id: string, status: MarketplaceStatus) => {
    setBusy(id);
    try {
      await api.adminSetItemStatus(id, status);
      toast.success(`Item ${status}.`);
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
        <SkeletonList module="admin" rows={4} />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">&gt; No items in this view.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.id} className="rounded-md border border-border bg-surface">
              <div className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium text-white">{item.name}</p>
                    <Badge domain={item.domain}>{item.domain}</Badge>
                    <Badge tone={item.status === 'published' ? 'cyan' : 'danger'}>
                      {item.status}
                    </Badge>
                  </div>
                  <p className="mt-1 font-mono text-xs text-muted">
                    {item.installs} installs · {item.rating_count} reviews
                    {item.author_id ? ` · author ${item.author_id.slice(0, 8)}` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {item.status !== 'published' ? (
                    <Button
                      variant="outline"
                      module="admin"
                      loading={busy === item.id}
                      onClick={() => void setStatus(item.id, 'published')}
                    >
                      Reinstate
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="ghost"
                        disabled={busy === item.id}
                        onClick={() => void setStatus(item.id, 'hidden')}
                      >
                        Hide
                      </Button>
                      <Button
                        variant="danger-outline"
                        disabled={busy === item.id}
                        onClick={() => void setStatus(item.id, 'removed')}
                      >
                        Remove
                      </Button>
                    </>
                  )}
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setExpanded((cur) => (cur === item.id ? undefined : item.id))
                    }
                  >
                    {expanded === item.id ? 'Hide reviews' : 'Reviews'}
                  </Button>
                </div>
              </div>
              {expanded === item.id && <ReviewList itemId={item.id} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
