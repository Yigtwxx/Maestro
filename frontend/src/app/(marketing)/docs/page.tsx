import Link from 'next/link';
import { ArrowRight, BookOpen, Heart, Network, Terminal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Reveal } from '@/components/effects/Reveal';
import { Card } from '@/components/ui/Card';
import { Markdown } from '@/components/ui/Markdown';
import { buttonVariants } from '@/components/ui/Button';
import { MarketingPage, PageHeader } from '@/components/landing/MarketingSection';
import {
  DOCS_ARCHITECTURE,
  DOCS_COMMUNITY,
  DOCS_QUICKSTART,
} from '@/lib/marketing-content';
import { GITHUB_SPONSORS_URL, GITHUB_URL } from '@/lib/constants';
import { cn } from '@/lib/cn';
import { buildPageMetadata } from '@/lib/seo/metadata';

export const metadata = buildPageMetadata({
  title: 'Docs',
  description:
    'Run Maestro locally in two commands, understand how a task flows through the agent hierarchy, and find the source.',
  path: '/docs',
});

interface DocsSection {
  icon: LucideIcon;
  content: string;
}

const SECTIONS: readonly DocsSection[] = [
  { icon: Terminal, content: DOCS_QUICKSTART },
  { icon: Network, content: DOCS_ARCHITECTURE },
  { icon: BookOpen, content: DOCS_COMMUNITY },
] as const;

export default function DocsPage() {
  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ DOCS ]"
        title="Everything runs on your"
        titleAccent="machine"
        description="Two commands bring the whole stack up. Bring your own model keys, or drive everything with a local model through Ollama."
      />

      <div className="mt-14 space-y-4">
        {SECTIONS.map((section, i) => (
          <Reveal key={i} delay={i * 0.05}>
            <Card className="flex gap-5 p-6">
              <section.icon
                className="mt-1 hidden h-5 w-5 shrink-0 text-primary sm:block"
                aria-hidden
              />
              <Markdown content={section.content} className="min-w-0 flex-1" />
            </Card>
          </Reveal>
        ))}
      </div>

      <Reveal className="mt-14">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-surface/50 p-8 text-center">
          <p className="font-mono text-xs leading-relaxed text-muted">
            Maestro is built in the open. Star it, break it, or help build it.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: 'lime' }), 'gap-1.5')}
            >
              View source
              <ArrowRight className="h-4 w-4" aria-hidden />
            </a>
            <a
              href={GITHUB_SPONSORS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={cn(buttonVariants({ variant: 'sponsor-outline' }), 'gap-1.5')}
            >
              <Heart className="h-4 w-4" aria-hidden />
              Sponsor
            </a>
            <Link
              href="/how-it-works"
              className={cn(buttonVariants({ variant: 'ghost' }), 'gap-1.5')}
            >
              How it works
            </Link>
          </div>
        </div>
      </Reveal>
    </MarketingPage>
  );
}
