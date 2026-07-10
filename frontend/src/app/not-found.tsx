import Link from 'next/link';
import { Button } from '@/components/ui/Button';

/**
 * Custom 404. Rendered inside the root layout for any unknown URL, replacing
 * Next's unbranded default with the app's cyber-terminal look.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <div className="w-full max-w-md">
        <p className="font-mono text-sm text-primary">&gt; 404 // ROUTE NOT FOUND</p>
        <h1 className="mt-3 text-3xl font-bold text-white">Lost in the mesh.</h1>
        <p className="mt-3 font-mono text-xs leading-relaxed text-muted">
          The route you requested does not exist or has moved.
        </p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <Link href="/">
            <Button variant="lime">Go home</Button>
          </Link>
          <Link href="/dashboard">
            <Button variant="ghost">Dashboard</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
