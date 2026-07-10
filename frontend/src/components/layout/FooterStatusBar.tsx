import Link from 'next/link';

const SEPARATOR = <span className="mx-2 text-border-bright">|</span>;

export function FooterStatusBar() {
  return (
    <footer className="flex h-9 shrink-0 items-center justify-between border-t border-border bg-surface px-6">
      <span className="text-micro text-muted">© 2026 MAESTRO — ORCHESTRATION LAYER</span>
      <span className="text-micro flex items-center text-muted">
        <span className="relative mr-1.5 flex h-1.5 w-1.5" aria-hidden>
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60 motion-reduce:hidden" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-primary" />
        </span>
        <span className="text-primary">Status: %99.9</span>
        {SEPARATOR}
        <Link href="/legal" className="transition-colors hover:text-white">
          Legal
        </Link>
        {SEPARATOR}
        <Link href="/privacy" className="transition-colors hover:text-white">
          Privacy
        </Link>
        {SEPARATOR}Terminal_V1
      </span>
    </footer>
  );
}
