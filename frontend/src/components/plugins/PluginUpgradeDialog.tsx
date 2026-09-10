'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowUpCircle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { PluginInstall, PluginUpgradeResult } from '@/types';

interface PluginUpgradeDialogProps {
  install?: PluginInstall;
  onClose: () => void;
  onUpgraded: () => Promise<void> | void;
}

const KIND_LABEL = {
  skill: 'Skill',
  mcp_server: 'MCP server',
  agent: 'Agent',
} as const;

const ACTION_LABEL = {
  created: 'new',
  updated: 'updated',
  unchanged: 'unchanged',
  removed: 'no longer in this version',
  conflict: 'partly updated',
} as const;

/**
 * The preview before an upgrade writes anything.
 *
 * It runs the real upgrade with `dry_run`, so what is listed here is produced
 * by the same code that will apply it — a separate preview path is a preview
 * that can drift. Conflicts are the part worth reading: a field the new version
 * changed *and* the user had changed is left alone rather than overwritten, and
 * this is the only place that decision is visible.
 */
export function PluginUpgradeDialog({
  install,
  onClose,
  onUpgraded,
}: PluginUpgradeDialogProps) {
  const [preview, setPreview] = useState<PluginUpgradeResult | undefined>();
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const load = useCallback(async () => {
    if (!install) {
      setPreview(undefined);
      return;
    }
    setLoading(true);
    try {
      setPreview(await api.upgradePlugin(install.id, true));
    } catch (err) {
      toast.error(
        err instanceof ApiError
          ? err.message
          : 'Could not check for an update.',
      );
    } finally {
      setLoading(false);
    }
  }, [install]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async () => {
    if (!install) return;
    setApplying(true);
    try {
      const result = await api.upgradePlugin(install.id, false);
      toast.success(`${install.name} updated to v${result.to_version}.`);
      await onUpgraded();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Update failed.');
    } finally {
      setApplying(false);
    }
  };

  const conflicts =
    preview?.changes.filter((c) => c.conflicted.length > 0) ?? [];
  const interesting =
    preview?.changes.filter((c) => c.action !== 'unchanged') ?? [];

  return (
    <Modal
      open={Boolean(install)}
      onClose={onClose}
      label={install ? `Update ${install.name}` : 'Update plugin'}
      className="max-w-2xl"
    >
      <div className="grid gap-4">
        {loading ? (
          <p className="text-xs text-muted">Checking for an update…</p>
        ) : preview ? (
          <>
            <p className="text-sm text-white">
              <code className="text-xs text-muted">
                v{preview.from_version}
              </code>{' '}
              →{' '}
              <code className="text-xs text-muted">v{preview.to_version}</code>
            </p>

            {!preview.changed ? (
              <p className="text-xs text-muted">
                Nothing to apply — you are already on the latest version of
                everything this plugin ships.
              </p>
            ) : (
              <div>
                <p className="text-micro text-muted">[ WHAT WILL CHANGE ]</p>
                <ul className="mt-2 grid gap-1.5">
                  {interesting.map((change) => (
                    <li
                      key={`${change.kind}:${change.slug}`}
                      className="text-xs"
                    >
                      <span className="text-white">
                        {KIND_LABEL[change.kind]}
                      </span>{' '}
                      <span className="text-muted">
                        — {change.name} ({ACTION_LABEL[change.action]})
                      </span>
                      {change.applied.length > 0 && (
                        <span className="text-muted/70">
                          {' '}
                          · {change.applied.join(', ')}
                        </span>
                      )}
                      {change.conflicted.length > 0 && (
                        <span className="text-warning">
                          {' '}
                          · keeping your {change.conflicted.join(', ')}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {conflicts.length > 0 && (
              <p className="flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/5 p-3 text-xs text-warning">
                <AlertTriangle
                  className="mt-0.5 h-3.5 w-3.5 shrink-0"
                  aria-hidden
                />
                <span>
                  The new version changes some fields you had edited yourself.
                  Yours are kept — the update will not overwrite them. Edit them
                  by hand afterwards if you want the new values.
                </span>
              </p>
            )}

            <p className="text-xs text-muted/70">
              Anything this version dropped is left in place rather than
              deleted. If an MCP server moved to a new address, its stored
              credential is cleared and the server disabled — a new address is
              not somewhere your token should follow automatically.
            </p>
          </>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={applying}
          >
            Close
          </Button>
          <Button
            type="button"
            variant="solid"
            module="marketplace"
            loading={applying}
            disabled={!preview?.changed}
            onClick={() => void run()}
          >
            <ArrowUpCircle className="h-3.5 w-3.5" aria-hidden />
            Apply update
          </Button>
        </div>
      </div>
    </Modal>
  );
}
