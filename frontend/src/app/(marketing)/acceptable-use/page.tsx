import { LegalDocument } from '@/components/legal/LegalDocument';
import { legalDoc } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

const doc = legalDoc('acceptable-use');

export const metadata = buildPageMetadata({
  title: doc.title,
  description: doc.description,
  path: `/${doc.slug}`,
});

export default function AcceptableUsePage() {
  return <LegalDocument doc={doc} title="Acceptable Use" titleAccent="Policy" />;
}
