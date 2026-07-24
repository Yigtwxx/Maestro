'use client';

import Link from 'next/link';
import { CreditCard } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { useAuthStore } from '@/stores/auth';

/** Read-only plan snapshot with a link to the billing screen. */
export function SubscriptionCard() {
  const user = useAuthStore((s) => s.user);

  return (
    <Card module="profile">
      <CardHeader icon={<CreditCard className="h-5 w-5" />} module="profile">
        <CardTitle>Subscription</CardTitle>
      </CardHeader>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <p className="text-sm text-muted">Current plan</p>
          {user &&
            (user.subscription_tier ? (
              <Badge module="profile">{user.subscription_tier}</Badge>
            ) : (
              <span className="text-sm text-muted">none</span>
            ))}
        </div>
        <Link href="/settings/billing">
          <Button variant="outline" module="profile">
            Manage billing
          </Button>
        </Link>
      </div>
    </Card>
  );
}
