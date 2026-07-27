'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AgentGraph,
  type ApiReach,
  type GraphNode,
  type NodeState,
} from '@/components/architect/AgentGraph';
import type { ConnectedLane } from '@/components/architect/ConnectedRail';
import { AgentCatalog } from '@/components/architect/AgentCatalog';
import { EventLog } from '@/components/architect/EventLog';
import { TaskRail } from '@/components/architect/TaskRail';
import { TaskDetailModal } from '@/components/architect/TaskDetailModal';
import { PanelRail, type PanelKey } from '@/components/architect/PanelRail';
import { CopyButton } from '@/components/ui/CopyButton';
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
import { useReducedMotion } from '@/lib/motion';
import { plainTextUncertainty } from '@/lib/uncertainty';
import {
  CONNECTED_TOOL_PROVIDERS,
  KEYLESS_CONNECTED_TOOLS,
  TASK_PROVIDERS,
} from '@/lib/constants';
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
function freezeState(
  state: NodeState,
  status: TaskStatus | undefined,
): NodeState {
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
  const [connectedProviders, setConnectedProviders] = useState<Set<string>>(
    new Set(),
  );
  const [step, setStep] = useState<WizardStep>('select');
  // undefined = no choice yet; null = "Automatic (Orchestrator)" chosen explicitly.
  const [selectedDomain, setSelectedDomain] = useState<
    string | null | undefined
  >(undefined);
  const [allowQuestions, setAllowQuestions] = useState(false);
  // Seeded from the user's saved default once it loads; then theirs per task.
  const [tracingEnabled, setTracingEnabled] = useState(false);
  const [reply, setReply] = useState('');
  // Task history dot the user clicked; drives the detail dialog.
  const [detailTaskId, setDetailTaskId] = useState<string>();
  // Which step-2 side panel is expanded; undefined means both sit on the rail
  // and the canvas takes their width. Config starts open — there is no prompt yet.
  // Exception: if a task is already running when this page (re)mounts — the user
  // left mid-run and navigated back — the panels stay collapsed on the rail, the
  // same as `onStart` leaves them, so the config does not pop itself back open.
  const [openPanel, setOpenPanel] = useState<PanelKey | undefined>(() =>
    isTaskRunning(useTaskStore.getState().status) ? undefined : 'config',
  );

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
  const clearActive = useTaskStore((s) => s.clearActive);
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

  // Pull the finished answer into view. Only for a task watched live: opening a
  // finished one from history also sets `answer`, and yanking the canvas away
  // from under a deliberate click is not the same gesture at all. The id of the
  // task last seen running is what tells the two apart — `answer` alone cannot,
  // since both paths set it in a single commit.
  const resultRef = useRef<HTMLDivElement>(null);
  const liveTaskId = useRef<string | undefined>(undefined);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    if (running && taskId) {
      liveTaskId.current = taskId;
      return;
    }
    // `answer` and the terminal status are written by one `set()` in the store,
    // so `running` is already false here while the ref still holds the id from
    // the previous commit — which is exactly the completion edge.
    if (!answer || !taskId || liveTaskId.current !== taskId) return;
    liveTaskId.current = undefined; // once per task, not on every later render
    resultRef.current?.scrollIntoView({
      behavior: reducedMotion ? 'auto' : 'smooth',
      block: 'start',
    });
  }, [running, taskId, answer, reducedMotion]);

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

  // Same one-shot seeding for the tracing toggle. False here still falls back to
  // the server-wide TRACING_ENABLED, so an operator who turned it on globally
  // keeps tracing everything unless the user explicitly switches this off.
  const defaultTracing = useAuthStore((s) => s.user?.default_tracing_enabled);
  const seededTracing = useRef(false);
  useEffect(() => {
    if (!seededTracing.current && defaultTracing !== undefined && !running) {
      setTracingEnabled(defaultTracing);
      seededTracing.current = true;
    }
  }, [defaultTracing, running]);

  useEffect(() => {
    // Best-effort: without the catalog, automatic mode still works.
    api
      .listAgents()
      .then((list) => setAgents(list.builtin.map(localizeBuiltinAgent)))
      .catch(() => setAgents([]));
    // Which BYOK services this account has connected — only the provider name
    // ever leaves the backend, never the key. Drives the connected rail's
    // "connect this" state, so a lane a squad could have used but could not is
    // visible while the task runs rather than only in settings.
    api
      .listApiKeys()
      .then((keys) =>
        setConnectedProviders(new Set(keys.map((k) => k.provider))),
      )
      .catch(() => setConnectedProviders(new Set()));
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

  // Connected-API traffic, folded in one pass: how many calls each provider
  // took, whether one is in flight, and which subagents reached for it. Every
  // tool call emits twice (`done: false` then `done: true`), so an in-flight
  // call is a start with no matching completion.
  const apiTraffic = useMemo(() => {
    const perProvider = new Map<
      string,
      { calls: number; inFlight: number; members: Set<number> }
    >();
    const perPair = new Map<
      string,
      { nodeKey: string; provider: string; inFlight: number }
    >();
    for (const e of events) {
      if (
        e.type !== 'agent_message' ||
        e.role !== 'subagent' ||
        typeof e.index !== 'number' ||
        typeof e.provider !== 'string' ||
        !e.provider
      ) {
        continue;
      }
      const lane = perProvider.get(e.provider) ?? {
        calls: 0,
        inFlight: 0,
        members: new Set<number>(),
      };
      const pairKey = `sub-${e.index}:${e.provider}`;
      const pair = perPair.get(pairKey) ?? {
        nodeKey: `sub-${e.index}`,
        provider: e.provider,
        inFlight: 0,
      };
      if (e.done) {
        lane.calls += 1;
        lane.inFlight = Math.max(0, lane.inFlight - 1);
        pair.inFlight = Math.max(0, pair.inFlight - 1);
      } else {
        lane.inFlight += 1;
        pair.inFlight += 1;
      }
      lane.members.add(e.index);
      perProvider.set(e.provider, lane);
      perPair.set(pairKey, pair);
    }
    return { perProvider, perPair };
  }, [events]);

  // Rail lanes: every connected API the routed squad *could* reach, whether or
  // not it did. Derived from the squad's declared tools rather than from the
  // event stream, because a tool with no key is withheld before it can emit
  // anything — and a lane the user could have had is exactly what is worth
  // showing.
  // Falls back to the picked squad before a task starts, so the rail answers
  // "which APIs will this squad reach" at configure time and not only mid-run.
  // Automatic routing leaves `selectedDomain` null, so nothing is guessed.
  const lanes = useMemo<ConnectedLane[]>(() => {
    const laneDomain = domain ?? selectedDomain ?? undefined;
    const routedAgent = agents.find((a) => a.domain === laneDomain);
    if (!routedAgent) return [];
    const out: ConnectedLane[] = [];
    for (const tool of routedAgent.tools) {
      const providers = CONNECTED_TOOL_PROVIDERS[tool];
      if (!providers) continue;
      const keyless = KEYLESS_CONNECTED_TOOLS.includes(tool);
      for (const provider of providers) {
        const traffic = apiTraffic.perProvider.get(provider);
        out.push({
          provider,
          calls: traffic?.calls ?? 0,
          active: (traffic?.inFlight ?? 0) > 0,
          available: keyless || connectedProviders.has(provider),
          members: traffic?.members.size ?? 0,
        });
      }
    }
    return out;
  }, [agents, domain, selectedDomain, apiTraffic, connectedProviders]);

  // One branch per (member, provider) pair, so four members hitting the same
  // API draw four lines and one member calling it six times draws one.
  const reaches = useMemo<ApiReach[]>(
    () =>
      Array.from(apiTraffic.perPair.values()).map((pair) => ({
        nodeKey: pair.nodeKey,
        provider: pair.provider,
        active: pair.inFlight > 0,
      })),
    [apiTraffic],
  );

  // Failed nodes plus non-fatal degradations (a fallback ran, the provider link
  // is retrying). Nodes are counted once each: a member re-run after a rejected
  // review can report the same failure twice.
  const warningCount = useMemo(() => {
    const failedNodes = new Set<string>();
    let warnings = 0;
    for (const e of events) {
      if (e.type === 'agent_warning') warnings += 1;
      else if (e.type === 'node_update' && e.state === 'error') {
        failedNodes.add(`${e.role ?? ''}:${e.index ?? ''}`);
      }
    }
    return warnings + failedNodes.size;
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
    // Both panels drop to the rail so the agent canvas gets the full width for
    // the run itself; they stay collapsed after it finishes.
    setOpenPanel(undefined);
    void startTask({
      prompt,
      provider,
      reviewer_enabled: reviewerEnabled,
      allow_questions: allowQuestions,
      tracing_enabled: tracingEnabled,
      domain: selectedDomain ?? undefined,
    });
  }, [
    prompt,
    provider,
    reviewerEnabled,
    allowQuestions,
    tracingEnabled,
    selectedDomain,
    startTask,
  ]);

  const onCancel = useCallback(() => void cancelTask(), [cancelTask]);

  const onTogglePanel = useCallback((panel: PanelKey) => {
    setOpenPanel((cur) => (cur === panel ? undefined : panel));
  }, []);

  // An unanswered agent question blocks the task, so it must never sit behind a
  // collapsed rail. Derived rather than pushed into state on an effect: the
  // panel reverts to whatever the user had open the moment the answer lands.
  const shownPanel = question ? 'config' : openPanel;

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

  // The white cap on the rail: detach from whatever is on the canvas and go
  // back to the expert picker. `clearActive` (not `reset`) keeps the history.
  const onNewTask = useCallback(() => {
    clearActive();
    setSelectedDomain(undefined);
    setPrompt('');
    setStep('select');
  }, [clearActive]);

  const onReply = useCallback(() => {
    if (!reply.trim()) return;
    replyToQuestion(reply.trim());
    setReply('');
  }, [reply, replyToQuestion]);

  const handleSelectDomain = useCallback((domain: string | null) => {
    setSelectedDomain(domain);
    setStep('configure');
    // Entering step 2 always shows the form full-size; it only drops to the
    // rail once the task actually starts.
    setOpenPanel('config');
  }, []);

  const selectedAgent = useMemo(
    () => agents.find((a) => a.domain === selectedDomain),
    [agents, selectedDomain],
  );
  // Resolved from `history` rather than stored, so a deleted task closes the
  // dialog on its own instead of stranding a stale copy.
  const detailTask = useMemo(
    () => history.find((t) => t.task_id === detailTaskId),
    [history, detailTaskId],
  );
  const promptPlaceholder = selectedAgent
    ? `Write your task for ${selectedAgent.name} — e.g. ${selectedAgent.capabilities[0] ?? 'your task'}…`
    : 'E.g. Summarize the latest developments in AI and list 3 takeaways.';

  return (
    <div className="grid gap-6 px-6 pt-5 pb-8 lg:grid-cols-[56px_minmax(0,1fr)]">
      <TaskRail
        items={history}
        loading={historyLoading}
        activeTaskId={taskId}
        onSelect={setDetailTaskId}
        onNewTask={onNewTask}
      />

      <TaskDetailModal
        task={detailTask}
        onClose={() => setDetailTaskId(undefined)}
        onOpenInCanvas={onSelectTask}
        onDelete={onDeleteTask}
      />

      <div>
        {step === 'select' ? (
          /* Step 1 — expert picker: an agent must be chosen before the task form appears */
          <div key="select" className="animate-fade-in">
            <p className={`text-micro mb-1 ${mc.text}`}>
              [ STEP 1/2 — EXPERT SELECTION ]
            </p>
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="text-sm text-muted">
                Pick an expert before starting the task. If unsure, use the
                Automatic (Orchestrator) option.
              </p>
              {/* The cards themselves are buttons, so their API chips cannot be
                  links. This is the one place the connect path lives. */}
              <Link
                href="/settings/api-keys"
                className="text-sm text-accent hover:underline"
              >
                Manage API keys →
              </Link>
            </div>
            <div data-onboarding="agent-catalog">
              <AgentCatalog
                agents={agents}
                selected={selectedDomain}
                onSelect={handleSelectDomain}
                connectedProviders={connectedProviders}
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
                  {selectedAgent
                    ? selectedAgent.name
                    : 'Automatic (Orchestrator)'}
                </span>
              </div>
              <div className="flex items-center gap-3">
                {status && <Badge status={status} />}
                <Button
                  variant="ghost"
                  onClick={() => setStep('select')}
                  disabled={running}
                  title={
                    running
                      ? 'The expert cannot be changed while a task is running'
                      : undefined
                  }
                >
                  Change
                </Button>
              </div>
            </div>

            <div
              className={cn(
                'panel-grid grid gap-6',
                shownPanel
                  ? 'lg:grid-cols-[minmax(0,1fr)_436px]'
                  : 'lg:grid-cols-[minmax(0,1fr)_56px]',
              )}
            >
              {/* Canvas — live agent map on grid backdrop */}
              <div>
                <div
                  className={cn(
                    'relative min-h-[420px] overflow-hidden rounded-lg border border-border bg-surface xl:min-h-[540px]',
                    'transition-shadow duration-700',
                    status === 'completed' &&
                      'border-module-architect/40 shadow-glow-mod-architect',
                  )}
                >
                  <div
                    className="canvas-depth absolute inset-0 rounded-lg"
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
                        {warningCount > 0 && (
                          // With the log collapsed to its rail this is the only
                          // visible sign anything went wrong, so it opens the log.
                          <button
                            type="button"
                            onClick={() => setOpenPanel('log')}
                            className="mr-auto rounded border border-warning/40 bg-warning/10 px-2 py-0.5 text-micro text-warning transition-colors hover:border-warning"
                          >
                            ⚠ {warningCount}{' '}
                            {warningCount === 1 ? 'warning' : 'warnings'}
                          </button>
                        )}
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
                    <AgentGraph
                      {...graph}
                      domain={domain}
                      lanes={lanes}
                      reaches={reaches}
                    />
                  </div>
                </div>

                {/* Live synthesis — the answer streams in via agent_delta chunks
                  before the final task_completed event lands. Hidden once the
                  whole answer arrives (it replaces this preview). */}
                {!answer && running && streamingAnswer && (
                  <div className="mt-6 rounded-lg border border-module-architect/40 bg-surface p-5">
                    <p className={`text-micro mb-2 ${mc.text}`}>
                      [ SYNTHESIZING ]
                    </p>
                    <Markdown content={streamingAnswer} markUncertainty streaming />
                    <span className="animate-blink text-module-architect">
                      ▊
                    </span>
                  </div>
                )}

                {/* Result — blur-in reveal with the animated gradient frame.
                  Carries the scroll target for the auto-scroll effect above. */}
                {answer && (
                  <Reveal onMount ref={resultRef}>
                    <div
                      className="gradient-border mt-6 rounded-lg p-5 shadow-glow-mod-architect"
                      style={{ ['--gb-rgb' as string]: mc.rgb }}
                    >
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <p className={`text-micro ${mc.text}`}>[ RESULT ]</p>
                        <CopyButton
                          value={plainTextUncertainty(answer)}
                          label="Copy result as Markdown"
                          module="architect"
                          className="-mt-1 -mr-1"
                        />
                      </div>
                      <Markdown content={answer} markUncertainty />
                    </div>
                  </Reveal>
                )}
              </div>

              {/* Config panel + log. From lg up they collapse into PanelRail and
                only the open one is mounted; below lg the rail is hidden and
                both stay stacked under the canvas as before. */}
              <div className="flex flex-col gap-6 lg:h-full lg:flex-row lg:gap-4">
                <div
                  id="architect-config-panel"
                  className={cn(
                    'flex flex-col gap-6 lg:min-w-0 lg:flex-1',
                    shownPanel !== 'config' && 'lg:hidden',
                  )}
                >
                  {/* Human-in-the-loop question — pops in and glows for attention.
                  It sits at the top of the config panel because an unanswered
                  question blocks the task, and the rail auto-opens this panel. */}
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
                          className="min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-sm text-white placeholder:text-muted/60 focus:border-accent focus:outline-none"
                        />
                        <Button variant="cyan-outline" onClick={onReply}>
                          Reply
                        </Button>
                      </div>
                    </div>
                  )}

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
                      <ToggleRow
                        label="Execution tracing"
                        checked={tracingEnabled}
                        onChange={setTracingEnabled}
                      />
                      {tracingEnabled && (
                        <p className="-mt-2 text-xs text-muted">
                          Records a span waterfall with per-call tokens and
                          cost. Open it from{' '}
                          <Link
                            href="/traces"
                            className="text-module-traces transition-colors hover:text-white"
                          >
                            Traces
                          </Link>{' '}
                          once the task finishes.
                        </p>
                      )}
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
                        <p className="text-sm text-danger">
                          &gt; ERROR: {error}
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                {/* The log is unmounted while collapsed rather than hidden: its
                  rows have a hard ~100px minimum width and would force a
                  horizontal scrollbar in the rail. Remounting also re-pins it
                  to the bottom, which its scroll effect does not do on resize. */}
                <div
                  id="architect-log-panel"
                  className={cn(
                    'flex min-h-0 flex-col lg:min-w-0 lg:flex-1',
                    shownPanel !== 'log' && 'lg:hidden',
                  )}
                >
                  <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-surface p-5">
                    <p className={`text-micro mb-3 ${mc.text}`}>[ LIVE LOG ]</p>
                    <div className="min-h-64 flex-1">
                      <EventLog
                        events={events}
                        staticCount={staticEventCount}
                      />
                    </div>
                  </div>
                </div>

                <PanelRail
                  className="hidden lg:flex"
                  open={shownPanel}
                  onToggle={onTogglePanel}
                  summary={{
                    agentName: selectedAgent
                      ? selectedAgent.name
                      : 'Automatic (Orchestrator)',
                    provider,
                    prompt,
                  }}
                  eventCount={events.length}
                  running={running}
                  onCancel={onCancel}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
