import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Reveal } from '@/components/effects/Reveal';
import { Card, CardDescription, CardTitle } from '@/components/ui/Card';
import { MarketingPage, PageHeader } from '@/components/landing/MarketingSection';
import { formatLegalDate, LEGAL_DOCS, LEGAL_ENTITY } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

export const metadata = buildPageMetadata({
  title: 'Legal',
  description:
    'Terms of Service, Privacy Policy, Security, Acceptable Use, and Cookie Policy for Maestro.',
  path: '/legal',
});

export default function LegalPage() {
  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ LEGAL ]"
        title="The fine print, written to be"
        titleAccent="read"
        description="Everything governing your use of Maestro, in one place. No dark patterns, no buried clauses."
      />

      <div className="mt-14 grid gap-4 sm:grid-cols-2">
        {LEGAL_DOCS.map((doc, i) => (
          <Reveal key={doc.slug} delay={i * 0.05}>
            <Link href={`/${doc.slug}`} className="group block h-full">
              <Card className="flex h-full flex-col p-6 transition-colors group-hover:border-border-bright">
                <CardTitle className="flex items-center gap-2">
                  {doc.title}
                  <ArrowRight
                    className="h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
                    aria-hidden
                  />
                </CardTitle>
                <CardDescription className="mt-2 flex-1">
                  {doc.description}
                </CardDescription>
                <p className="mt-4 font-mono text-xs text-muted">
                  Updated {formatLegalDate(doc.updated)}
                </p>
              </Card>
            </Link>
          </Reveal>
        ))}
      </div>

      <Reveal className="mt-14">
        <div className="rounded-lg border border-border bg-surface/50 p-8 text-center">
          <p className="font-mono text-xs leading-relaxed text-muted">
            Questions about any of this? Write to{' '}
            <a
              href={`mailto:${LEGAL_ENTITY.contactEmail}`}
              className="text-accent underline underline-offset-2 hover:text-accent/80"
            >
              {LEGAL_ENTITY.contactEmail}
            </a>
            .
          </p>
        </div>
      </Reveal>
    </MarketingPage>
  );
}
