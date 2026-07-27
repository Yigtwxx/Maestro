import Link from 'next/link';

const SEPARATOR = <span className="mx-2 text-border-bright">|</span>;

export function FooterStatusBar() {
  return (
    <footer className="flex h-9 shrink-0 items-center justify-between border-t border-border bg-surface px-6">
      <span className="text-micro text-muted">© 2026 MAESTRO — ORCHESTRATION LAYER</span>
      <span className="text-micro flex items-center text-muted">
        <Link href="/legal" className="transition-colors hover:text-white">
          Legal
        </Link>
        {SEPARATOR}
        <Link href="/privacy" className="transition-colors hover:text-white">
          Privacy
        </Link>
      </span>
    </footer>
  );
}
