import { AlertTriangle } from 'lucide-react';
import { Reveal } from '@/components/effects/Reveal';
import { Card } from '@/components/ui/Card';
import { LegalBody } from '@/components/legal/LegalBody';
import { MarketingPage, PageHeader } from '@/components/landing/MarketingSection';
import { formatLegalDate, type LegalDoc } from '@/lib/legal';

interface LegalDocumentProps {
  doc: LegalDoc;
  /** Plain leading words of the page title. */
  title: string;
  /** Trailing words carrying the brand gradient sweep. */
  titleAccent?: string;
  /** Standing caveats shown above the text (pre-release billing, pending KVKK). */
  notices?: readonly string[];
  /** Interactive extras below the prose (e.g. the consent manager on /cookies). */
  children?: React.ReactNode;
}

/** The shell every legal page renders: header, date, caveats, then the prose. */
export function LegalDocument({ doc, title, titleAccent, notices, children }: LegalDocumentProps) {
  return (
    <MarketingPage>
      <PageHeader
        eyebrow="[ LEGAL ]"
        title={title}
        titleAccent={titleAccent}
        description={doc.description}
      />

      <p className="mt-6 text-center font-mono text-xs text-muted">
        Last updated: {formatLegalDate(doc.updated)}
      </p>

      {notices !== undefined && notices.length > 0 && (
        <Reveal className="mt-8">
          <div className="space-y-3">
            {notices.map((notice) => (
              <div
                key={notice}
                className="flex gap-3 rounded-lg border border-danger/40 bg-danger/5 p-4"
              >
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-danger"
                  aria-hidden
                />
                <p className="font-mono text-xs leading-relaxed text-slate-200">
                  {notice}
                </p>
              </div>
            ))}
          </div>
        </Reveal>
      )}

      <Reveal className="mt-10">
        <Card className="p-6 sm:p-8">
          <LegalBody
            content={doc.content}
            locale={doc.locale}
            translations={doc.translations}
          />
        </Card>
      </Reveal>

      {children !== undefined && <Reveal className="mt-8">{children}</Reveal>}
    </MarketingPage>
  );
}
