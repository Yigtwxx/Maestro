'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ShieldAlert } from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import { cn } from '@/lib/cn';
import { MODULE_COLOR } from '@/lib/module-colors';
import { useAuthStore } from '@/stores/auth';

const mc = MODULE_COLOR['admin'];

const TABS = [
  { href: '/admin', label: 'Overview' },
  { href: '/admin/reports', label: 'Reports' },
  { href: '/admin/marketplace', label: 'Marketplace' },
  { href: '/admin/users', label: 'Users' },
  { href: '/admin/audit', label: 'Audit' },
];

/**
 * Role gate + tab chrome for the moderation surface. The outer `(app)` layout
 * already enforces authentication; this adds the admin-role check. The role is
 * read from the hydrated profile, so non-admins are bounced to the dashboard.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const hydrated = useAuthStore((s) => s.hydrated);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (hydrated && user && user.role !== 'admin') {
      router.replace('/dashboard');
    }
  }, [hydrated, user, router]);

  if (!hydrated || !user || user.role !== 'admin') {
    return (
      <PageShell>
        <p className="font-mono text-sm text-muted">&gt; Verifying moderator access…</p>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="mb-5 flex items-center gap-2">
        <ShieldAlert className={cn('h-5 w-5', mc.text)} aria-hidden />
        <h1 className="text-lg font-bold text-white">Moderation</h1>
      </div>
      <nav className="mb-6 flex flex-wrap gap-1 border-b border-border">
        {TABS.map((tab) => {
          const active =
            tab.href === '/admin'
              ? pathname === '/admin'
              : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
                active
                  ? cn(mc.text, 'border-module-admin')
                  : 'border-transparent text-muted hover:text-white',
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </PageShell>
  );
}
