import { LegalDocument } from '@/components/legal/LegalDocument';
import { legalDoc } from '@/lib/legal';
import { buildPageMetadata } from '@/lib/seo/metadata';

const doc = legalDoc('cookies');

export const metadata = buildPageMetadata({
  title: doc.title,
  description: doc.description,
  path: `/${doc.slug}`,
});

export default function CookiesPage() {
  return <LegalDocument doc={doc} title="Cookie" titleAccent="Policy" />;
}
