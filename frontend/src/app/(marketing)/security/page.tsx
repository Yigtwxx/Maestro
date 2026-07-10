import { LegalDocument } from '@/components/legal/LegalDocument';
import { legalDoc } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

const doc = legalDoc('security');

export const metadata = buildPageMetadata({
  title: doc.title,
  description: doc.description,
  path: `/${doc.slug}`,
});

export default function SecurityPage() {
  return <LegalDocument doc={doc} title="How we hold your" titleAccent="keys" />;
}
