'use client';

import { useCallback, useEffect, useState } from 'react';
import { Package, PackagePlus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { Stagger, StaggerItem } from '@/components/effects/Stagger';
import { PageShell } from '@/components/layout/PageShell';
import { PluginInstallDialog } from '@/components/plugins/PluginInstallDialog';
import { PluginUninstallDialog } from '@/components/plugins/PluginUninstallDialog';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { Plugin, PluginDetail, PluginInstall } from '@/types';

// Reuses the marketplace module hue rather than claiming one of its own: a
// plugin catalog *is* a marketplace surface, and a new ModuleKey costs a
// hand-written Tailwind literal set mirrored twice in tailwind.config.ts.
const MODULE = 'marketplace' as const;

export default function PluginsPage() {
  const [catalog, setCatalog] = useState<Plugin[]>([]);
  const [installed, setInstalled] = useState<PluginInstall[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [detail, setDetail] = useState<PluginDetail | undefined>();
  const [removing, setRemoving] = useState<PluginInstall | undefined>();
  const [importUrl, setImportUrl] = useState('');
  const [importing, setImporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [browse, mine] = await Promise.all([
        api.listPlugins(),
        api.listInstalledPlugins(),
      ]);
      setCatalog(browse);
      setInstalled(mine);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Plugins could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const installedIds = new Set(installed.map((row) => row.plugin_id));

  const openDetail = async (plugin: Plugin) => {
    try {
      setDetail(await api.getPlugin(plugin.id));
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : 'That plugin could not be read.',
      );
    }
  };

  const runImport = async (e: React.FormEvent) => {
    e.preventDefault();
    setImporting(true);
    try {
      const result = await api.importPlugin(importUrl);
      toast.success(`${result.name} installed.`);
      setImportUrl('');
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Import failed.');
    } finally {
      setImporting(false);
    }
  };

  return (
    <PageShell>
      <div className="mb-4">
        <p className="text-micro text-module-marketplace">[ PLUGINS ]</p>
        <p className="mt-1 text-xs text-muted/80">
          A plugin installs a whole way of working at once — skills, MCP servers
          and agents together. It carries declarations only: no code, and never
          a credential, so a server it brings arrives for you to connect
          yourself.
        </p>
      </div>

      {error && <p className="mb-3 text-sm text-danger">&gt; ERROR: {error}</p>}

      {installed.length > 0 && (
        <section className="mb-8">
          <p className="mb-3 text-micro text-muted">[ INSTALLED ]</p>
          <ul className="grid gap-3">
            {installed.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-surface-2/50 p-3"
              >
                <div>
                  <p className="text-sm text-white">
                    {row.name}{' '}
                    <code className="text-xs text-muted">v{row.version}</code>
                  </p>
                  <p className="mt-0.5 text-xs text-muted/70">
                    {row.created_skill_ids.length} skills ·{' '}
                    {row.created_mcp_server_ids.length} servers ·{' '}
                    {row.created_agent_ids.length} agents
                    {row.source === 'url' && row.origin_url
                      ? ` · imported from ${new URL(row.origin_url).host}`
                      : ''}
                  </p>
                  {row.needs_credentials.length > 0 && (
                    <p className="mt-1 text-xs text-warning">
                      {row.needs_credentials.length} server
                      {row.needs_credentials.length === 1 ? '' : 's'} still need
                      {row.needs_credentials.length === 1 ? 's' : ''} your
                      credential — add it under the agent wizard&apos;s
                      Capabilities step before they will run.
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  onClick={() => setRemoving(row)}
                  aria-label={`Remove ${row.name}`}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mb-8">
        <p className="mb-3 text-micro text-muted">[ IMPORT FROM A URL ]</p>
        <form onSubmit={runImport} className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <Input
              label="Manifest URL"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="https://example.com/maestro-plugin.json"
              module={MODULE}
            />
          </div>
          <Button
            type="submit"
            variant="outline"
            module={MODULE}
            loading={importing}
            disabled={!importUrl}
          >
            <PackagePlus className="h-3.5 w-3.5" aria-hidden />
            Import
          </Button>
        </form>
        <p className="mt-2 text-xs text-warning">
          A plugin imported from a URL has not been reviewed by Maestro, and the
          address can serve something different tomorrow. Install one only from
          a source you trust. Your deployment may have this turned off.
        </p>
      </section>

      <section>
        <p className="mb-3 text-micro text-muted">[ CATALOG ]</p>
        {loading ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : catalog.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-2/30 px-4 py-10 text-center">
            <Package className="h-5 w-5 text-muted" aria-hidden />
            <p className="max-w-sm text-xs text-muted">
              Nothing published yet.
            </p>
          </div>
        ) : (
          <Stagger className="grid gap-3 sm:grid-cols-2">
            {catalog.map((plugin) => (
              <StaggerItem key={plugin.id}>
                <Card>
                  <CardHeader>
                    <CardTitle>{plugin.name}</CardTitle>
                    <p className="text-xs text-muted">
                      v{plugin.version} · {plugin.author_label} ·{' '}
                      {plugin.installs} install
                      {plugin.installs === 1 ? '' : 's'}
                    </p>
                  </CardHeader>
                  <p className="text-xs text-muted/80">{plugin.description}</p>
                  <div className="mt-3">
                    <Button
                      variant="outline"
                      module={MODULE}
                      disabled={installedIds.has(plugin.plugin_id)}
                      onClick={() => void openDetail(plugin)}
                    >
                      {installedIds.has(plugin.plugin_id)
                        ? 'Installed'
                        : 'Review & install'}
                    </Button>
                  </div>
                </Card>
              </StaggerItem>
            ))}
          </Stagger>
        )}
      </section>

      <PluginInstallDialog
        plugin={detail}
        onClose={() => setDetail(undefined)}
        onInstalled={async () => {
          setDetail(undefined);
          await load();
        }}
      />
      <PluginUninstallDialog
        install={removing}
        onClose={() => setRemoving(undefined)}
        onRemoved={async () => {
          setRemoving(undefined);
          await load();
        }}
      />
    </PageShell>
  );
}
