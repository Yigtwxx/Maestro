'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { AccountLocked } from '@/components/layout/AccountLocked';
import { Sidebar } from '@/components/layout/Sidebar';
import { TaskFavicon } from '@/components/layout/TaskFavicon';
import { TopBar } from '@/components/layout/TopBar';
import { FooterStatusBar } from '@/components/layout/FooterStatusBar';
import { VerifyEmailBanner } from '@/components/layout/VerifyEmailBanner';
import { OnboardingCoachmark } from '@/components/onboarding/OnboardingCoachmark';
import { ProgressBar } from '@/components/ui/ProgressBar';
import DecryptedText from '@/components/DecryptedText';
import { useAuthStore } from '@/stores/auth';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const hydrate = useAuthStore((s) => s.hydrate);
  const hydrated = useAuthStore((s) => s.hydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const deletionRequestedAt = useAuthStore((s) => s.user?.deletion_requested_at);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      router.replace('/login');
    }
  }, [hydrated, isAuthenticated, router]);

  if (!hydrated || !isAuthenticated) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-grid">
        <p className="font-mono text-sm text-primary">
          &gt;{' '}
          <DecryptedText
            text="MAESTRO OS LOADING"
            animateOn="view"
            sequential
            speed={35}
            encryptedClassName="text-primary/50"
          />
          <span className="animate-blink">_</span>
        </p>
        <ProgressBar className="w-56" color="lime" />
      </div>
    );
  }

  // Every product endpoint 403s while the account is locked, so short-circuit
  // the app rather than render a shell that cannot load anything.
  if (deletionRequestedAt) {
    return <AccountLocked requestedAt={deletionRequestedAt} />;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <TaskFavicon />
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <VerifyEmailBanner />
        <TopBar />
        <main className="flex-1 overflow-y-auto">{children}</main>
        <FooterStatusBar />
      </div>
      <OnboardingCoachmark />
    </div>
  );
}
