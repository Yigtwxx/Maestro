'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion } from 'motion/react';
import {
  Workflow,
  Activity,
  CreditCard,
  LayoutDashboard,
  Store,
  Bot,
  FileText,
  KeyRound,
  LogOut,
  Rocket,
  ShieldAlert,
  UserRound,
} from 'lucide-react';
import { BrandMark } from '@/components/brand/BrandMark';
import { Avatar } from '@/components/ui/Avatar';
import { cn } from '@/lib/cn';
import { MODULE_COLOR, type ModuleKey } from '@/lib/module-colors';
import { SPRING, useReducedMotion } from '@/lib/motion';
import { useAuthStore } from '@/stores/auth';

export const NAV: { href: string; label: string; icon: typeof Workflow; module: ModuleKey }[] = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, module: 'dashboard' },
  { href: '/marketplace', label: 'Marketplace', icon: Store, module: 'marketplace' },
  { href: '/architect', label: 'Architect', icon: Workflow, module: 'architect' },
  { href: '/traces', label: 'Traces', icon: Activity, module: 'traces' },
  { href: '/agents', label: 'Agents', icon: Bot, module: 'agents' },
  { href: '/documents', label: 'Documents', icon: FileText, module: 'documents' },
  { href: '/settings/api-keys', label: 'API Keys', icon: KeyRound, module: 'api-keys' },
  { href: '/settings/billing', label: 'Billing', icon: CreditCard, module: 'billing' },
  { href: '/settings/profile', label: 'Profile', icon: UserRound, module: 'profile' },
];

// The admin surface is appended to the nav only for admins. Exported so TopBar
// can resolve its section label without duplicating the definition.
export const ADMIN_LINK: (typeof NAV)[number] = {
  href: '/admin',
  label: 'Admin',
  icon: ShieldAlert,
  module: 'admin',
};

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);
  const reduced = useReducedMotion();

  const nav = user?.role === 'admin' ? [...NAV, ADMIN_LINK] : NAV;

  const onLogout = () => {
    logout();
    router.replace('/login');
  };

  return (
    <aside className="flex w-48 shrink-0 flex-col border-r border-border bg-surface">
      {/* `h-14` mirrors the TopBar so the two bottom borders meet across the
          sidebar seam. Padding-driven height drifted 12px out of line. */}
      <div className="flex h-14 items-center gap-3 border-b border-border px-5">
        <BrandMark className="h-9 w-9 shrink-0 rounded" glyphClassName="h-5 w-5" />
        <div className="leading-tight">
          <span className="block font-sans text-base font-bold tracking-wide text-white">
            MAESTRO
          </span>
          {/* Tighter and smaller than `text-micro` — as a wordmark subtitle it
              only has to whisper, and the wide tracking read as a second title. */}
          <span className="block text-[9px] font-semibold uppercase tracking-[0.08em] text-primary">
            AI OS v0.2
          </span>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {nav.map((item) => {
          const active = pathname.startsWith(item.href);
          const Icon = item.icon;
          const mc = MODULE_COLOR[item.module];
          return (
            <Link
              key={item.href}
              href={item.href}
              data-onboarding={
                item.href === '/settings/api-keys'
                  ? 'nav-api-keys'
                  : item.href === '/architect'
                    ? 'nav-architect'
                    : undefined
              }
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
        {user && (
          <Link
            href="/settings/profile"
            className={cn(
              'flex items-center gap-3 rounded-md px-2 py-2 transition-colors',
              'hover:bg-surface-2',
              pathname.startsWith('/settings/profile') && 'bg-surface-2',
            )}
          >
            <Avatar
              displayName={user.display_name}
              email={user.email}
              color={user.avatar_color}
              emoji={user.avatar_emoji}
              size="md"
            />
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-medium text-white">
                {user.display_name || user.email}
              </span>
              <span className="block truncate text-micro capitalize text-muted">
                {user.subscription_tier ? `${user.subscription_tier} plan` : 'No plan'}
              </span>
            </span>
          </Link>
        )}
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
