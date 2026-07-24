'use client';

import { useEffect, useState } from 'react';
import { MonitorSmartphone, Smartphone, Monitor, LogOut } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { SkeletonList } from '@/components/ui/Skeleton';
import { api, ApiError } from '@/lib/api';
import { relativeTime } from '@/lib/date';
import { toast } from '@/stores/toast';
import type { SessionInfo } from '@/types';

function DeviceIcon({ device }: { device: string }) {
  const mobile = /Android|iOS|iPadOS/i.test(device);
  const Icon = mobile ? Smartphone : Monitor;
  return <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden />;
}

/** Active login sessions, with per-session and bulk revocation. */
export function SessionsCard() {
  const [sessions, setSessions] = useState<SessionInfo[] | undefined>();
  const [error, setError] = useState<string | undefined>();
  const [busyId, setBusyId] = useState<string | undefined>();
  const [revokingOthers, setRevokingOthers] = useState(false);

  const load = async () => {
    setError(undefined);
    try {
      setSessions(await api.listSessions());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sessions could not be loaded.');
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onRevoke = async (id: string) => {
    setBusyId(id);
    try {
      await api.revokeSession(id);
      setSessions((prev) => prev?.filter((s) => s.id !== id));
      toast.success('Session signed out.');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not revoke session.');
    } finally {
      setBusyId(undefined);
    }
  };

  const onRevokeOthers = async () => {
    setRevokingOthers(true);
    try {
      await api.revokeOtherSessions();
      setSessions((prev) => prev?.filter((s) => s.current));
      toast.success('Signed out of all other devices.');
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not revoke sessions.');
    } finally {
      setRevokingOthers(false);
    }
  };

  const otherCount = sessions?.filter((s) => !s.current).length ?? 0;

  return (
    <Card module="profile">
      <CardHeader icon={<MonitorSmartphone className="h-5 w-5" />} module="profile">
        <CardTitle>Active Sessions</CardTitle>
      </CardHeader>

      {error && <p className="text-sm text-danger">&gt; ERROR: {error}</p>}

      {sessions === undefined && !error ? (
        <SkeletonList rows={2} module="profile" />
      ) : (
        <div className="space-y-3">
          {sessions?.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface-2 px-3 py-2.5"
            >
              <div className="flex min-w-0 items-center gap-3">
                <DeviceIcon device={s.device} />
                <div className="min-w-0 leading-tight">
                  <p className="flex items-center gap-2 truncate text-sm text-white">
                    {s.device}
                    {s.current && (
                      <Badge tone="cyan" dot>
                        This device
                      </Badge>
                    )}
                  </p>
                  <p className="truncate text-micro text-muted">
                    {s.ip ?? 'Unknown IP'} ·{' '}
                    {s.last_used_at
                      ? `active ${relativeTime(s.last_used_at)}`
                      : `signed in ${relativeTime(s.created_at)}`}
                  </p>
                </div>
              </div>
              {!s.current && (
                <Button
                  variant="danger-outline"
                  className="shrink-0"
                  loading={busyId === s.id}
                  onClick={() => onRevoke(s.id)}
                >
                  Revoke
                </Button>
              )}
            </div>
          ))}

          {otherCount > 0 && (
            <Button
              variant="outline"
              module="profile"
              className="gap-1.5"
              loading={revokingOthers}
              onClick={onRevokeOthers}
            >
              <LogOut className="h-4 w-4" aria-hidden />
              Sign out all other devices
            </Button>
          )}
        </div>
      )}
    </Card>
  );
}
