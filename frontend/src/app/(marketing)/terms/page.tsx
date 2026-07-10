import { LegalDocument } from '@/components/legal/LegalDocument';
import { BILLING_LIVE, BILLING_PRERELEASE_NOTICE, legalDoc } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

const doc = legalDoc('terms');

export const metadata = buildPageMetadata({
  title: doc.title,
  description: doc.description,
  path: `/${doc.slug}`,
});

export default function TermsPage() {
  return (
    <LegalDocument
      doc={doc}
      title="Terms of"
      titleAccent="Service"
      notices={BILLING_LIVE ? undefined : [BILLING_PRERELEASE_NOTICE]}
    />
  );
}
