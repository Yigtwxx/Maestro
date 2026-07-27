import { describe, it, expect, beforeEach } from 'vitest';
import { isTaskRunning, useTaskStore } from '@/stores/tasks';
import { TERMINAL_STATUSES } from '@/lib/constants';
import type { AgentEvent, TaskStatus } from '@/types';

// applyEvent is a reducer over untyped wire events; build minimal ones.
const ev = (e: Record<string, unknown>): AgentEvent => e as unknown as AgentEvent;
const apply = (e: Record<string, unknown>): void =>
  useTaskStore.getState().applyEvent(ev(e));

beforeEach(() => {
  useTaskStore.setState({
    status: undefined,
    streamingAnswer: '',
    answer: undefined,
    question: undefined,
    error: undefined,
  });
});

describe('isTaskRunning', () => {
  it('is false without a status', () => {
    expect(isTaskRunning(undefined)).toBe(false);
  });

  it('is true for a non-terminal status', () => {
    expect(isTaskRunning('running')).toBe(true);
    expect(isTaskRunning('pending')).toBe(true);
    expect(isTaskRunning('awaiting_answer')).toBe(true);
  });

  it('is false for every terminal status', () => {
    for (const status of TERMINAL_STATUSES) {
      expect(isTaskRunning(status), status).toBe(false);
    }
  });
});

describe('applyEvent', () => {
  it('accumulates agent_delta chunks into the streaming answer', () => {
    apply({ type: 'agent_delta', text: 'Hel' });
    apply({ type: 'agent_delta', text: 'lo' });
    expect(useTaskStore.getState().streamingAnswer).toBe('Hello');
  });

  it('sets a question on agent_question and clears it on user_answer', () => {
    apply({ type: 'agent_question', question: 'Which region?' });
    expect(useTaskStore.getState().question).toBe('Which region?');
    apply({ type: 'user_answer' });
    expect(useTaskStore.getState().question).toBeUndefined();
  });

  it('settles on task_completed with the final answer', () => {
    apply({ type: 'agent_question', question: 'q' });
    apply({ type: 'task_completed', answer: 'done' });
    const state = useTaskStore.getState();
    expect(state.status).toBe('completed');
    expect(state.answer).toBe('done');
    expect(state.question).toBeUndefined();
  });

  it('treats task_completed_with_warnings as a terminal state with an answer', () => {
    // Regression: this status is terminal (partial failure still yields an
    // answer); a non-terminal status here would spin forever.
    apply({ type: 'task_completed_with_warnings', answer: 'partial' });
    const state = useTaskStore.getState();
    expect(state.status).toBe('completed_with_warnings');
    expect(state.answer).toBe('partial');
    expect(TERMINAL_STATUSES.has('completed_with_warnings')).toBe(true);
    expect(isTaskRunning('completed_with_warnings')).toBe(false);
  });

  it('settles on task_cancelled', () => {
    apply({ type: 'task_cancelled', error: 'stopped' });
    expect(useTaskStore.getState().status).toBe('cancelled');
    expect(useTaskStore.getState().error).toBe('stopped');
  });

  it('prefers the wire status carried on task_failed', () => {
    const cases: Array<[string, TaskStatus]> = [
      ['timeout', 'timeout'],
      ['failed', 'failed'],
      ['cancelled', 'cancelled'],
    ];
    for (const [wire, expected] of cases) {
      useTaskStore.setState({ status: 'running' });
      apply({ type: 'task_failed', status: wire, error: 'x' });
      expect(useTaskStore.getState().status, wire).toBe(expected);
    }
  });

  it('keeps an optimistic cancel when task_failed carries no wire status', () => {
    useTaskStore.setState({ status: 'cancelled' });
    apply({ type: 'task_failed' });
    expect(useTaskStore.getState().status).toBe('cancelled');
  });

  it('falls back to failed when neither wire status nor optimistic cancel apply', () => {
    useTaskStore.setState({ status: 'running' });
    apply({ type: 'task_failed' });
    expect(useTaskStore.getState().status).toBe('failed');
  });
});
