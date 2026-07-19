'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import { useAuthStore } from '@/stores/auth';
import type { AdminUserRow } from '@/types';

export default function AdminUsersPage() {
  const me = useAuthStore((s) => s.user);
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await api.adminListUsers(query.trim() || undefined));
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Users could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (id: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id);
    try {
      await fn();
      toast.success(ok);
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Action failed.');
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
        className="flex gap-2"
      >
        <Input
          label="Search by email"
          placeholder="user@example.com"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          module="admin"
          className="flex-1"
        />
      </form>

      {loading ? (
        <SkeletonList module="admin" rows={4} />
      ) : users.length === 0 ? (
        <p className="text-sm text-muted">&gt; No users found.</p>
      ) : (
        <ul className="space-y-2">
          {users.map((u) => {
            const isSelf = u.id === me?.id;
            const suspended = u.suspended_at !== null;
            return (
              <li
                key={u.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface p-4"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium text-white">{u.email}</p>
                    {u.role === 'admin' && <Badge module="admin">admin</Badge>}
                    {suspended && <Badge tone="danger">suspended</Badge>}
                    {u.deletion_requested_at && <Badge tone="gray">deleting</Badge>}
                  </div>
                  <p className="mt-1 font-mono text-xs text-muted">
                    {u.subscription_tier ? `${u.subscription_tier} plan` : 'no plan'}
                    {u.email_verified ? ' · verified' : ' · unverified'}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {suspended ? (
                    <Button
                      variant="outline"
                      module="admin"
                      loading={busy === u.id}
                      onClick={() =>
                        void act(u.id, () => api.adminUnsuspendUser(u.id), 'Unsuspended.')
                      }
                    >
                      Unsuspend
                    </Button>
                  ) : (
                    <Button
                      variant="danger-outline"
                      disabled={isSelf || busy === u.id}
                      onClick={() =>
                        void act(u.id, () => api.adminSuspendUser(u.id), 'Suspended.')
                      }
                    >
                      Suspend
                    </Button>
                  )}
                  {u.role === 'admin' ? (
                    <Button
                      variant="ghost"
                      disabled={isSelf || busy === u.id}
                      onClick={() =>
                        void act(u.id, () => api.adminSetUserRole(u.id, 'user'), 'Demoted.')
                      }
                    >
                      Demote
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      disabled={busy === u.id}
                      onClick={() =>
                        void act(u.id, () => api.adminSetUserRole(u.id, 'admin'), 'Promoted.')
                      }
                    >
                      Make admin
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
