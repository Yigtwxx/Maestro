'use client';

import { useCallback, useEffect, useState } from 'react';
import { BookOpen, Plus, ShieldAlert } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { Modal } from '@/components/ui/Modal';
import { SkillForm } from '@/components/agents/wizard/SkillForm';
import { api, ApiError } from '@/lib/api';
import { cn } from '@/lib/cn';
import type { Skill, ToolCatalogItem } from '@/types';

interface SkillListProps {
  /** Ids this agent has attached. */
  selected: string[];
  onChange: (ids: string[]) => void;
  max: number;
  /** The catalog, used both by the form and by the missing-tool warning. */
  tools: ToolCatalogItem[];
  /** Tools the agent currently enables, for the same warning. */
  agentTools: string[];
}

export function SkillList({
  selected,
  onChange,
  max,
  tools,
  agentTools,
}: SkillListProps) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Skill | undefined>();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | undefined>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSkills(await api.listSkills());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Skills could not be loaded.',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: string, on: boolean) => {
    if (on && selected.length >= max) return;
    onChange(on ? [...selected, id] : selected.filter((entry) => entry !== id));
  };

  const remove = async (skill: Skill) => {
    setError(undefined);
    try {
      await api.deleteSkill(skill.id);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `${skill.name} could not be deleted.`,
      );
      return;
    }
    onChange(selected.filter((entry) => entry !== skill.id));
    await load();
  };

  const labelFor = (id: string) =>
    tools.find((tool) => tool.id === id)?.label ?? id;

  const atLimit = selected.length >= max;

  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-micro text-module-agents">[ SKILLS ]</p>
          <p className="mt-1 text-xs text-muted/80">
            Reusable working instructions. Write one once, attach it to as many
            agents as you like. Up to {max} per agent.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          module="agents"
          onClick={() => setCreating(true)}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
          Add skill
        </Button>
      </div>

      {error && <p className="mb-3 text-sm text-danger">&gt; ERROR: {error}</p>}

      {loading ? (
        <p className="text-xs text-muted">Loading your skills…</p>
      ) : skills.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border bg-surface-2/30 px-4 py-8 text-center">
          <BookOpen className="h-5 w-5 text-muted" aria-hidden />
          <p className="max-w-sm text-xs text-muted">
            No skills yet. A skill is the method you would otherwise retype into
            every agent&apos;s prompt.
          </p>
        </div>
      ) : (
        <ul className="grid gap-3">
          {skills.map((skill) => {
            const checked = selected.includes(skill.id);
            const missing = checked
              ? skill.required_tools.filter((id) => !agentTools.includes(id))
              : [];
            return (
              <li
                key={skill.id}
                className={cn(
                  'rounded-md border p-3 transition-colors',
                  checked
                    ? 'border-module-agents/50 bg-module-agents/5'
                    : 'border-border bg-surface-2/50',
                )}
              >
                <Checkbox
                  module="agents"
                  checked={checked}
                  disabled={!checked && atLimit}
                  onChange={(e) => toggle(skill.id, e.target.checked)}
                  label={
                    <span className="flex flex-wrap items-baseline gap-2">
                      {skill.name}
                      <code className="text-xs text-muted">
                        v{skill.version}
                      </code>
                    </span>
                  }
                  hint={skill.description || undefined}
                />

                <div className="mt-2 flex flex-wrap items-center gap-2 pl-[26px]">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setEditing(skill)}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => void remove(skill)}
                  >
                    Delete
                  </Button>
                </div>

                {!skill.security_scan_passed && (
                  <p className="mt-2 flex items-start gap-1.5 pl-[26px] text-xs text-danger">
                    <ShieldAlert
                      className="mt-0.5 h-3.5 w-3.5 shrink-0"
                      aria-hidden
                    />
                    This skill fails the current injection scan, so it is
                    withheld from every run. Edit the instructions to restore
                    it.
                  </p>
                )}

                {missing.length > 0 && (
                  <p className="mt-2 pl-[26px] text-xs text-warning">
                    Expects {missing.map(labelFor).join(', ')} — this agent does
                    not enable{' '}
                    {missing.length === 1 ? 'that tool' : 'those tools'}. The
                    skill still applies; turn{' '}
                    {missing.length === 1 ? 'it' : 'them'} on above if you want
                    the method to work as written.
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {atLimit && (
        <p className="mt-2 text-xs text-warning">
          {max} skills attached — the cap keeps the agent&apos;s instructions
          from crowding out its own role. Unselect one to swap.
        </p>
      )}

      <Modal
        open={creating || Boolean(editing)}
        onClose={() => {
          setCreating(false);
          setEditing(undefined);
        }}
        label={editing ? 'Edit skill' : 'Create a skill'}
        className="max-w-2xl"
      >
        <SkillForm
          initial={editing}
          tools={tools}
          onCancel={() => {
            setCreating(false);
            setEditing(undefined);
          }}
          onSubmit={async (input) => {
            if (editing) {
              await api.updateSkill(editing.id, input);
            } else {
              const created = await api.createSkill(input);
              if (selected.length < max) onChange([...selected, created.id]);
            }
            setCreating(false);
            setEditing(undefined);
            await load();
          }}
        />
      </Modal>
    </section>
  );
}
