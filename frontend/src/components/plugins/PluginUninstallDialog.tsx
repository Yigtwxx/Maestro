'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { PluginInstall, PluginUninstallPreview } from '@/types';

interface PluginUninstallDialogProps {
  install?: PluginInstall;
  onClose: () => void;
  onRemoved: () => Promise<void> | void;
}

const KIND_LABEL = {
  skill: 'Skill',
  mcp_server: 'MCP server',
  agent: 'Agent',
} as const;

/**
 * The confirmation before a bundle deletes what it created.
 *
 * Removing a plugin removes its records — that is the behaviour, and it is why
 * this dialog fetches the preview rather than trusting the counts on the install
 * row. Records the user edited after installing are called out separately:
 * throwing away an agent whose prompt someone rewrote is destructive in a way a
 * "Remove" button does not communicate on its own.
 */
export function PluginUninstallDialog({
  install,
  onClose,
  onRemoved,
}: PluginUninstallDialogProps) {
  const [preview, setPreview] = useState<PluginUninstallPreview | undefined>();
  const [loading, setLoading] = useState(false);
  const [removing, setRemoving] = useState(false);

  const load = useCallback(async () => {
    if (!install) {
      setPreview(undefined);
      return;
    }
    setLoading(true);
    try {
      setPreview(await api.previewUninstallPlugin(install.id));
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : 'Could not read that plugin.',
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
    setRemoving(true);
    try {
      await api.uninstallPlugin(install.id);
      toast.success(`${install.name} removed.`);
      await onRemoved();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Removal failed.');
    } finally {
      setRemoving(false);
    }
  };

  const edited = preview?.members.filter((member) => member.edited) ?? [];

  return (
    <Modal
      open={Boolean(install)}
      onClose={onClose}
      label={install ? `Remove ${install.name}` : 'Remove plugin'}
      className="max-w-2xl"
    >
      <div className="grid gap-4">
        {loading ? (
          <p className="text-xs text-muted">Checking what this owns…</p>
        ) : preview ? (
          <>
            <div>
              <p className="text-micro text-muted">[ THIS WILL DELETE ]</p>
              {preview.members.length === 0 ? (
                <p className="mt-2 text-xs text-muted">
                  Nothing — every record this plugin created has already been
                  removed or detached.
                </p>
              ) : (
                <ul className="mt-2 grid gap-1">
                  {preview.members.map((member) => (
                    <li key={member.id} className="text-xs text-muted">
                      <span className="text-white">
                        {KIND_LABEL[member.kind]}
                      </span>{' '}
                      — {member.name}
                      {member.edited && (
                        <span className="text-warning"> (you edited this)</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {edited.length > 0 && (
              <p className="flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/5 p-3 text-xs text-warning">
                <AlertTriangle
                  className="mt-0.5 h-3.5 w-3.5 shrink-0"
                  aria-hidden
                />
                <span>
                  You changed {edited.length} of these after installing.
                  Removing the plugin deletes your edits with them.
                </span>
              </p>
            )}

            <p className="text-xs text-muted/70">
              Anything you created yourself, or detached from this plugin, is
              left alone.
            </p>
          </>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={removing}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="solid"
            module="marketplace"
            loading={removing}
            onClick={() => void run()}
          >
            Remove plugin
          </Button>
        </div>
      </div>
    </Modal>
  );
}
