'use client';

import { useEffect } from 'react';
import { IdentityCard } from '@/components/settings/IdentityCard';
import { AccountCard } from '@/components/settings/AccountCard';
import { SecurityCard } from '@/components/settings/SecurityCard';
import { TwoFactorCard } from '@/components/settings/TwoFactorCard';
import { SessionsCard } from '@/components/settings/SessionsCard';
import { PreferencesCard } from '@/components/settings/PreferencesCard';
import { SubscriptionCard } from '@/components/settings/SubscriptionCard';
import { DangerZoneCard } from '@/components/settings/DangerZoneCard';
import { PageShell } from '@/components/layout/PageShell';
import { useAuthStore } from '@/stores/auth';

export default function ProfilePage() {
  const refreshUser = useAuthStore((s) => s.refreshUser);

  // Pull the freshest profile once on mount so every card seeds from live data.
  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  return (
    <PageShell>
      <div className="space-y-6">
        <IdentityCard />
        <AccountCard />
        <SecurityCard />
        <TwoFactorCard />
        <SessionsCard />
        <PreferencesCard />
        <SubscriptionCard />
        <DangerZoneCard />
      </div>
    </PageShell>
  );
}
