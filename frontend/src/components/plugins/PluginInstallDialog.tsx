'use client';

import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { api, ApiError } from '@/lib/api';
import { toast } from '@/stores/toast';
import type { PluginDetail } from '@/types';

interface PluginInstallDialogProps {
  plugin?: PluginDetail;
  onClose: () => void;
  onInstalled: () => Promise<void> | void;
}

/**
 * The confirmation before a bundle writes anything.
 *
 * It lists every record the install will create, by name, because "install"
 * otherwise hides that a plugin is about to add up to twenty-five things to the
 * account. The credential notice is the other half: a manifest cannot carry a
 * secret, so a credentialed server arrives disabled and the user has to be told
 * that before they wonder why it does nothing.
 */
export function PluginInstallDialog({
  plugin,
  onClose,
  onInstalled,
}: PluginInstallDialogProps) {
  const [installing, setInstalling] = useState(false);

  const run = async () => {
    if (!plugin) return;
    setInstalling(true);
    try {
      await api.installPlugin(plugin.id);
      toast.success(`${plugin.name} installed.`);
      await onInstalled();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Install failed.');
    } finally {
      setInstalling(false);
    }
  };

  const manifest = plugin?.manifest;
  const needsCredentials =
    manifest?.mcp_servers.filter((server) => server.auth_mode !== 'none') ?? [];

  return (
    <Modal
      open={Boolean(plugin)}
      onClose={onClose}
      label={plugin ? `Install ${plugin.name}` : 'Install plugin'}
      className="max-w-2xl"
    >
      {manifest && (
        <div className="grid gap-4">
          <div>
            <p className="text-sm text-white">
              {manifest.name}{' '}
              <code className="text-xs text-muted">v{manifest.version}</code>
            </p>
            {manifest.description && (
              <p className="mt-1 text-xs text-muted/80">
                {manifest.description}
              </p>
            )}
          </div>

          <div>
            <p className="text-micro text-muted">[ THIS WILL CREATE ]</p>
            <ul className="mt-2 grid gap-1">
              {manifest.skills.map((skill) => (
                <li key={skill.slug} className="text-xs text-muted">
                  <span className="text-white">Skill</span> — {skill.name}
                </li>
              ))}
              {manifest.mcp_servers.map((server) => (
                <li key={server.slug} className="text-xs text-muted">
                  <span className="text-white">MCP server</span> — {server.name}{' '}
                  <code className="text-muted/70">
                    {new URL(server.url).host}
                  </code>
                </li>
              ))}
              {manifest.agents.map((agent) => (
                <li key={agent.slug} className="text-xs text-muted">
                  <span className="text-white">Agent</span> — {agent.name}
                </li>
              ))}
            </ul>
          </div>

          {needsCredentials.length > 0 && (
            <p className="flex items-start gap-1.5 rounded-md border border-warning/40 bg-warning/5 p-3 text-xs text-warning">
              <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>
                {needsCredentials.length} of these servers needs a credential a
                plugin is not allowed to carry. They will be installed disabled;
                add your own token and enable them from the agent wizard.
              </span>
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={installing}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="solid"
              module="marketplace"
              loading={installing}
              onClick={() => void run()}
            >
              Install
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
