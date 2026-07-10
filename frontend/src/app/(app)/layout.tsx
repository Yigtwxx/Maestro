'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { AccountLocked } from '@/components/layout/AccountLocked';
import { Sidebar } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { FooterStatusBar } from '@/components/layout/FooterStatusBar';
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
    hydrate();
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
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto">{children}</main>
        <FooterStatusBar />
      </div>
    </div>
  );
}
