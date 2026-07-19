'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AgentGraph,
  type GraphNode,
  type NodeState,
} from '@/components/architect/AgentGraph';
import { AgentCatalog } from '@/components/architect/AgentCatalog';
import { EventLog } from '@/components/architect/EventLog';
import { HistoryPanel } from '@/components/architect/HistoryPanel';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { Textarea } from '@/components/ui/Textarea';
import { Markdown } from '@/components/ui/Markdown';
import { Reveal } from '@/components/effects/Reveal';
import { cn } from '@/lib/cn';
import { api } from '@/lib/api';
import {
  describeSubagentActivity,
  localizeBuiltinAgent,
  memberDisplayName,
} from '@/lib/agent-locale';
import { MODULE_COLOR } from '@/lib/module-colors';
import { TASK_PROVIDERS } from '@/lib/constants';
import { useAuthStore } from '@/stores/auth';
import { isTaskRunning, useTaskStore } from '@/stores/tasks';
import type {
  AgentEvent,
  AssignmentBrief,
  BuiltinAgent,
  LLMProvider,
  TaskStatus,
} from '@/types';

// Fold node_update events into the latest state per (role, index) in one pass,
// so a graph with N nodes costs O(events) instead of O(events × nodes).
// The single reviewer node covers parallel per-subtask reviews: starts arrive
// as indexed node_update events, completions as review_result — so it is
// keyed without index and counted (running while any review is in flight).
function nodeStateMap(events: AgentEvent[]): Map<string, NodeState> {
  const states = new Map<string, NodeState>();
  let reviewsRunning = 0;
  for (const e of events) {
    if (e.type === 'review_result') {
      reviewsRunning = Math.max(0, reviewsRunning - 1);
      states.set('reviewer:', reviewsRunning > 0 ? 'running' : 'done');
      continue;
    }
    if (e.type !== 'node_update') continue;
    if (e.state === 'running' || e.state === 'done' || e.state === 'error') {
      if (e.role === 'reviewer') {
        if (e.state === 'running') reviewsRunning += 1;
        states.set('reviewer:', e.state);
      } else {
        states.set(`${e.role}:${e.index ?? ''}`, e.state);
      }
    }
  }
  return states;
}

function nodeStateOf(
  states: Map<string, NodeState>,
  role: string,
  index?: number,
): NodeState {
  return states.get(`${role}:${index ?? ''}`) ?? 'idle';
}

// When the task has stopped, no node may stay "running" — the backend sends no
// node_update to close in-flight nodes, so freeze lingering running nodes to a
// terminal look. This halts every running-driven animation at the source
// (edge pulses, ping ring, dashed edge, indeterminate progress bar).
function freezeState(state: NodeState, status: TaskStatus | undefined): NodeState {
  if (state !== 'running' || isTaskRunning(status)) return state;
  if (status === 'completed') return 'done';
  if (status === 'cancelled') return 'cancelled';
  return 'error'; // failed | timeout
}

const mc = MODULE_COLOR.architect;

/** Mockup-style toggle row: label + module-hue toggle chip instead of a bare checkbox. */
function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between rounded-md border border-border bg-surface-2 px-3 py-2 text-left text-sm text-slate-200 transition-colors hover:border-border-bright"
    >
      {label}
      <span
        className={cn(
          'text-micro rounded px-2 py-0.5',
          checked ? 'bg-module-architect text-black' : 'bg-surface text-muted',
        )}
      >
        {checked ? 'ON' : 'OFF'}
      </span>
    </button>
  );
}

type WizardStep = 'select' | 'configure';

export default function ArchitectPage() {
  const user = useAuthStore((s) => s.user);
  const [prompt, setPrompt] = useState('');
  // Default to the local model: a fresh user has no keys and default_provider
  // is null, so any BYOK provider would fail with "no key" on their first task.
  // The effect below upgrades this to the user's default brain once it loads.
  const [provider, setProvider] = useState<LLMProvider>('ollama');
  // Pre-select the user's default brain until they change it manually.
  const providerTouched = useRef(false);
  const [agents, setAgents] = useState<BuiltinAgent[]>([]);
  const [step, setStep] = useState<WizardStep>('select');
  // undefined = no choice yet; null = "Automatic (Orchestrator)" chosen explicitly.
  const [selectedDomain, setSelectedDomain] = useState<
    string | null | undefined
  >(undefined);
  const [allowQuestions, setAllowQuestions] = useState(false);
  const [reply, setReply] = useState('');

  // Task state lives in a module-level store, so navigating away and back no
  // longer discards the answer (App Router remounts this page every time).
  const events = useTaskStore((s) => s.events);
  const status = useTaskStore((s) => s.status);
  const answer = useTaskStore((s) => s.answer);
  const streamingAnswer = useTaskStore((s) => s.streamingAnswer);
  const error = useTaskStore((s) => s.error);
  const question = useTaskStore((s) => s.question);
  const taskId = useTaskStore((s) => s.activeTaskId);
  const staticEventCount = useTaskStore((s) => s.staticEventCount);
  const reviewerEnabled = useTaskStore((s) => s.reviewerEnabled);
  const history = useTaskStore((s) => s.history);
  const historyLoading = useTaskStore((s) => s.historyLoading);
  const setReviewerEnabled = useTaskStore((s) => s.setReviewerEnabled);
  const startTask = useTaskStore((s) => s.startTask);
  const openTask = useTaskStore((s) => s.openTask);
  const restoreTask = useTaskStore((s) => s.restore);
  const loadHistory = useTaskStore((s) => s.loadHistory);
  const cancelTask = useTaskStore((s) => s.cancelTask);
  const deleteTask = useTaskStore((s) => s.deleteTask);
  const replyToQuestion = useTaskStore((s) => s.replyToQuestion);

  const running = isTaskRunning(status);

  useEffect(() => {
    void loadHistory();
    // Reattaches to the task the user was last watching after a full reload.
    void restoreTask();
  }, [loadHistory, restoreTask]);

  // On (re)entering the page, resume straight to the canvas only if the last
  // task is still running; a finished (or absent) task leaves the expert picker
  // in front. Selecting a task from history is handled explicitly in
  // `onSelectTask`, so a finished task can still be reopened on demand.
  useEffect(() => {
    if (running) setStep('configure');
  }, [running]);

  // Seed the reviewer toggle from the user's preference once, before any task
  // runs. After that the toggle is the user's to flip per task; we never
  // override an in-flight task's setting.
  const defaultReviewer = useAuthStore((s) => s.user?.default_reviewer_enabled);
  const seededReviewer = useRef(false);
  useEffect(() => {
    if (!seededReviewer.current && defaultReviewer !== undefined && !running) {
      setReviewerEnabled(defaultReviewer);
      seededReviewer.current = true;
    }
  }, [defaultReviewer, running, setReviewerEnabled]);

  useEffect(() => {
    // Best-effort: without the catalog, automatic mode still works.
    api
      .listAgents()
      .then((list) => setAgents(list.builtin.map(localizeBuiltinAgent)))
      .catch(() => setAgents([]));
  }, []);

  useEffect(() => {
    if (user?.default_provider && !providerTouched.current) {
      setProvider(user.default_provider);
    }
  }, [user]);

  const routing = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].domain) return events[i];
    }
    return undefined;
  }, [events]);
  const domain = routing?.domain;
  const routedByUser = routing?.source === 'user';

  const assignments = useMemo(() => {
    let e: AgentEvent | undefined;
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (ev.type === 'agent_message' && (ev.assignments || ev.subtasks)) {
        e = ev;
        break;
      }
    }
    if (e?.assignments) return e.assignments;
    // Older events carry only briefs — synthesize nameless assignments.
    return (e?.subtasks ?? []).map((brief, i): AssignmentBrief => ({
      member_id: `sub-${i}`,
      member_name: `Subagent #${i}`,
      brief,
    }));
  }, [events]);

  // Latest tool activity per subagent index — one pass over the stream,
  // same shape as nodeStateMap.
  const subagentActivity = useMemo(() => {
    const latest = new Map<number, string>();
    for (const e of events) {
      if (
        e.type === 'agent_message' &&
        e.role === 'subagent' &&
        typeof e.index === 'number' &&
        e.action
      ) {
        latest.set(e.index, describeSubagentActivity(e));
      }
    }
    return latest;
  }, [events]);

  const graph = useMemo(() => {
    const states = nodeStateMap(events);
    const orchestrator: GraphNode = {
      key: 'orchestrator',
      label: 'Orchestrator',
      sublabel: domain
        ? routedByUser
          ? `User selection: ${domain}`
          : `domain: ${domain}`
        : 'Router',
      state: freezeState(nodeStateOf(states, 'orchestrator'), status),
    };
    const main: GraphNode = {
      key: 'main',
      label: 'Main Agent',
      sublabel: domain ? `${domain} expert` : 'Expert',
      state: freezeState(nodeStateOf(states, 'main'), status),
    };
    const subagents: GraphNode[] = assignments.map((assignment, i) => ({
      key: `sub-${i}`,
      // Backend sends raw member names; show the catalog UI name.
      label: memberDisplayName(
        domain,
        assignment.member_id,
        assignment.member_name,
      ),
      sublabel: assignment.brief,
      state: freezeState(nodeStateOf(states, 'subagent', i), status),
      details: {
        brief: assignment.brief,
        activity: subagentActivity.get(i),
        dependsOn: assignment.depends_on?.map((id) => {
          const dep = assignments.find((a) => a.member_id === id);
          return dep
            ? memberDisplayName(domain, dep.member_id, dep.member_name)
            : id;
        }),
      },
    }));
    const reviewer: GraphNode | undefined = reviewerEnabled
      ? {
          key: 'reviewer',
          label: 'Reviewer',
          sublabel: 'Auditor',
          state: freezeState(nodeStateOf(states, 'reviewer'), status),
        }
      : undefined;
    return { orchestrator, main, subagents, reviewer };
  }, [
    events,
    status,
    assignments,
    subagentActivity,
    domain,
    routedByUser,
    reviewerEnabled,
  ]);

  const onStart = useCallback(() => {
    if (!prompt.trim()) return;
    void startTask({
      prompt,
      provider,
      reviewer_enabled: reviewerEnabled,
      allow_questions: allowQuestions,
      domain: selectedDomain ?? undefined,
    });
  }, [
    prompt,
    provider,
    reviewerEnabled,
    allowQuestions,
    selectedDomain,
    startTask,
  ]);

  const onCancel = useCallback(() => void cancelTask(), [cancelTask]);

  const onSelectTask = useCallback(
    (id: string) => {
      // Explicit: opening any history item (even a finished one) shows its canvas.
      setStep('configure');
      void openTask(id);
    },
    [openTask],
  );

  const onDeleteTask = useCallback(
    (id: string) => void deleteTask(id),
    [deleteTask],
  );

  const onReply = useCallback(() => {
    if (!reply.trim()) return;
    replyToQuestion(reply.trim());
    setReply('');
  }, [reply, replyToQuestion]);

  const handleSelectDomain = useCallback((domain: string | null) => {
    setSelectedDomain(domain);
    setStep('configure');
  }, []);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.domain === selectedDomain),
    [agents, selectedDomain],
  );
  const promptPlaceholder = selectedAgent
    ? `Write your task for ${selectedAgent.name} — e.g. ${selectedAgent.capabilities[0] ?? 'your task'}…`
    : 'E.g. Summarize the latest developments in AI and list 3 takeaways.';

  return (
    <div className="grid gap-6 px-6 pt-5 pb-8 lg:grid-cols-[260px_minmax(0,1fr)]">
      <HistoryPanel
        items={history}
        loading={historyLoading}
        activeTaskId={taskId}
        onSelect={onSelectTask}
        onDelete={onDeleteTask}
      />

      <div>
      {step === 'select' ? (
        /* Step 1 — expert picker: an agent must be chosen before the task form appears */
        <div key="select" className="animate-fade-in">
          <p className={`text-micro mb-1 ${mc.text}`}>
            [ STEP 1/2 — EXPERT SELECTION ]
          </p>
          <p className="mb-4 text-sm text-muted">
            Pick an expert before starting the task. If unsure, use the
            Automatic (Orchestrator) option.
          </p>
          <div data-onboarding="agent-catalog">
            <AgentCatalog
              agents={agents}
              selected={selectedDomain}
              onSelect={handleSelectDomain}
              disabled={running}
            />
          </div>
        </div>
      ) : (
        /* Step 2 — selected-agent chip + task config, canvas and live log */
        <div key="configure" className="animate-fade-in">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="text-micro text-muted">
                [ STEP 2/2 — SELECTED EXPERT ]
              </span>
              <span className="rounded border border-module-architect/40 bg-module-architect/10 px-2 py-0.5 text-sm font-bold text-module-architect">
                {selectedAgent ? selectedAgent.name : 'Automatic (Orchestrator)'}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {status && <Badge status={status} />}
              <Button
                variant="ghost"
                onClick={() => setStep('select')}
                disabled={running}
                title={
                  running ? 'The expert cannot be changed while a task is running' : undefined
                }
              >
                Change
              </Button>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_420px]">
            {/* Canvas — live agent map on grid backdrop */}
            <div>
              <div
                className={cn(
                  'relative min-h-[420px] overflow-hidden rounded-lg border border-border bg-surface xl:min-h-[540px]',
                  'transition-shadow duration-700',
                  status === 'completed' && 'border-module-architect/40 shadow-glow-mod-architect',
                )}
              >
                <div
                  className="bg-grid absolute inset-0 rounded-lg"
                  style={{ ['--grid-rgb' as string]: mc.rgb }}
                  aria-hidden
                />
                {/* Power-on sweep, replayed per task. */}
                {running && taskId && (
                  <span
                    key={taskId}
                    aria-hidden
                    className="panel-scan"
                    style={{ ['--ps-rgb' as string]: mc.rgb }}
                  />
                )}
                <div className="relative p-5">
                  {taskId && (
                    <div className="mb-5 flex items-center justify-end gap-3">
                      <span className="text-micro text-muted">
                        TASK: {taskId.slice(0, 8)}…
                      </span>
                      <Link
                        href={`/traces?task=${taskId}`}
                        className="text-micro text-module-traces transition-colors hover:text-white"
                      >
                        View trace →
                      </Link>
                    </div>
                  )}
                  <AgentGraph {...graph} domain={domain} />
                </div>
              </div>

              {/* Live synthesis — the answer streams in via agent_delta chunks
                  before the final task_completed event lands. Hidden once the
                  whole answer arrives (it replaces this preview). */}
              {!answer && running && streamingAnswer && (
                <div
                  className="mt-6 rounded-lg border border-module-architect/40 bg-surface p-5"
                >
                  <p className={`text-micro mb-2 ${mc.text}`}>[ SYNTHESIZING ]</p>
                  <Markdown content={streamingAnswer} />
                  <span className="animate-blink text-module-architect">▊</span>
                </div>
              )}

              {/* Result — blur-in reveal with the animated gradient frame. */}
              {answer && (
                <Reveal onMount>
                  <div
                    className="gradient-border mt-6 rounded-lg p-5 shadow-glow-mod-architect"
                    style={{ ['--gb-rgb' as string]: mc.rgb }}
                  >
                    <p className={`text-micro mb-2 ${mc.text}`}>[ RESULT ]</p>
                    <Markdown content={answer} />
                  </div>
                </Reveal>
              )}
            </div>

            {/* Config panel + log */}
            <div className="flex flex-col gap-6">
              <div className="rounded-lg border border-border bg-surface p-5">
                <p className={`text-micro mb-4 ${mc.text}`}>
                  [ TASK CONFIGURATION ]
                </p>
                <div className="flex flex-col gap-4">
                  <Textarea
                    label={
                      selectedAgent
                        ? `Task Prompt — ${selectedAgent.name}`
                        : 'Task Prompt — Automatic routing'
                    }
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    rows={4}
                    placeholder={promptPlaceholder}
                    module="architect"
                    data-onboarding="task-prompt"
                  />
                  <Select
                    label="Model / Provider"
                    value={provider}
                    onChange={(e) => {
                      providerTouched.current = true;
                      setProvider(e.target.value as LLMProvider);
                    }}
                    options={TASK_PROVIDERS.map((p) => ({
                      value: p.id,
                      label: p.label,
                    }))}
                    module="architect"
                  />
                  {provider === 'ollama' && (
                    <p className="-mt-2 text-xs text-muted">
                      The local model needs an Ollama chat model on the
                      server. On the hosted instance it is unavailable — run
                      Maestro on your own machine with Ollama, or connect a
                      provider API key in Settings.
                    </p>
                  )}
                  <ToggleRow
                    label="Reviewer (auditor)"
                    checked={reviewerEnabled}
                    onChange={setReviewerEnabled}
                  />
                  <ToggleRow
                    label="Allow questions (HITL)"
                    checked={allowQuestions}
                    onChange={setAllowQuestions}
                  />
                  <div className="mt-1 flex flex-col gap-2">
                    <Button
                      variant="solid"
                      module="architect"
                      onClick={onStart}
                      loading={running}
                      className="w-full"
                      data-onboarding="start-task"
                    >
                      Start Task
                    </Button>
                    {running && (
                      <Button
                        variant="danger-outline"
                        onClick={onCancel}
                        className="w-full"
                      >
                        Cancel
                      </Button>
                    )}
                  </div>
                  {error && (
                    <p className="text-sm text-danger">&gt; ERROR: {error}</p>
                  )}
                </div>
              </div>

              {/* Human-in-the-loop question — pops in and glows for attention. */}
              {question && (
                <div className="animate-word-in rounded-lg border border-accent/50 bg-surface p-5 shadow-glow-cyan motion-reduce:animate-none">
                  <p className="text-micro mb-2 text-accent">
                    [ AGENT ASKING ]
                  </p>
                  <div className="mb-3">
                    <Markdown content={question} />
                  </div>
                  <div className="flex gap-2">
                    <input
                      value={reply}
                      onChange={(e) => setReply(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && onReply()}
                      placeholder="Type your answer…"
                      className="flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-sm text-white placeholder:text-muted/60 focus:border-accent focus:outline-none"
                    />
                    <Button variant="cyan-outline" onClick={onReply}>
                      Reply
                    </Button>
                  </div>
                </div>
              )}

              <div className="flex flex-1 flex-col rounded-lg border border-border bg-surface p-5">
                <p className={`text-micro mb-3 ${mc.text}`}>[ LIVE LOG ]</p>
                <div className="min-h-64 flex-1">
                  <EventLog events={events} staticCount={staticEventCount} />
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
