'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion } from 'motion/react';
import {
  Workflow,
  CreditCard,
  LayoutDashboard,
  Store,
  Bot,
  FileText,
  KeyRound,
  LogOut,
  Rocket,
  UserRound,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { MODULE_COLOR, type ModuleKey } from '@/lib/module-colors';
import { SPRING, useReducedMotion } from '@/lib/motion';
import { useAuthStore } from '@/stores/auth';

export const NAV: { href: string; label: string; icon: typeof Workflow; module: ModuleKey }[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, module: 'dashboard' },
  { href: '/marketplace', label: 'Marketplace', icon: Store, module: 'marketplace' },
  { href: '/architect', label: 'Architect', icon: Workflow, module: 'architect' },
  { href: '/agents', label: 'Agents', icon: Bot, module: 'agents' },
  { href: '/documents', label: 'Documents', icon: FileText, module: 'documents' },
  { href: '/settings/api-keys', label: 'API Keys', icon: KeyRound, module: 'settings' },
  { href: '/settings/billing', label: 'Billing', icon: CreditCard, module: 'settings' },
  { href: '/settings/profile', label: 'Profil', icon: UserRound, module: 'settings' },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const reduced = useReducedMotion();

  const onLogout = () => {
    logout();
    router.replace('/login');
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-primary font-sans text-lg font-bold text-black"
          aria-hidden
        >
          M
        </span>
        <div className="leading-tight">
          <span className="block font-sans text-base font-bold tracking-wide text-white">
            MAESTRO
          </span>
          <span className="text-micro text-primary">AI OS v0.2</span>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV.map((item) => {
          const active = pathname.startsWith(item.href);
          const Icon = item.icon;
          const mc = MODULE_COLOR[item.module];
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                active ? 'text-black' : 'text-muted hover:bg-surface-2 hover:text-white',
              )}
            >
              {/* Module-colored pill slides between nav items via shared layoutId. */}
              {active && (
                <motion.span
                  layoutId="nav-active"
                  aria-hidden
                  className={cn('absolute inset-0 rounded-md', mc.bgSolid, mc.glow)}
                  transition={reduced ? { duration: 0 } : SPRING.pop}
                />
              )}
              <Icon
                className={cn(
                  'relative z-10 h-4 w-4 shrink-0 transition-[color,transform]',
                  'motion-safe:group-hover:scale-110',
                  !active && mc.navIconHover,
                )}
                aria-hidden
              />
              <span className="relative z-10">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="space-y-2 border-t border-border p-3">
        <Link
          href="/architect"
          className={cn(
            'flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2',
            'text-sm font-semibold uppercase tracking-wide text-black',
            'transition-all hover:bg-primary-hover hover:shadow-glow-primary shimmer-hover',
          )}
        >
          <Rocket className="h-4 w-4" aria-hidden />
          Deploy Agent
        </Link>
        <button
          onClick={onLogout}
          className={cn(
            'flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted',
            'transition-colors hover:bg-surface-2 hover:text-white',
          )}
        >
          <LogOut className="h-4 w-4" aria-hidden />
          Sign out
        </button>
      </div>
    </aside>
  );
}
