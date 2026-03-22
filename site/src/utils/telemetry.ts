import { IDLE_SNAPSHOT, KNOWN_SUITE_ORDER } from '../constants.js';
import type {
  ActiveLoop,
  CanonicalAgent,
  DashboardSnapshot,
  DashboardTask,
  DashboardTestSuite,
  RawDashboardPayload,
  RawTask,
} from '../types.js';
import {
  getPipelineStageForAgent,
  normalizeAgent,
  normalizeResearchMode,
} from '../workers.js';

function toPositiveNumber(value: number | string | null | undefined): number {
  const numeric = typeof value === 'string' ? Number(value) : value;
  if (!Number.isFinite(numeric) || Number(numeric) < 0) {
    return 0;
  }
  return Number(numeric);
}

function normalizeActiveLoop(value: string | undefined): ActiveLoop {
  return value === 'research' ? 'research' : 'orchestration';
}

function normalizeTaskStatus(value: string | undefined): DashboardTask['status'] {
  if (value === 'complete') {
    return 'complete';
  }
  if (value === 'active') {
    return 'active';
  }
  return 'pending';
}

function normalizeTask(
  rawTask: RawTask | undefined,
  activeLoop: ActiveLoop,
  researchMode: DashboardSnapshot['loop']['researchMode'],
): DashboardTask {
  const status = normalizeTaskStatus(rawTask?.status);
  return {
    id: rawTask?.id ?? '',
    name: rawTask?.name?.trim() || '—',
    status,
    activeAgent: normalizeAgent(rawTask?.active_agent, activeLoop, researchMode),
  };
}

function normalizeTestSuites(
  rawTests: RawDashboardPayload['tests'],
): Record<string, DashboardTestSuite> {
  const orderedKeys = rawTests
    ? [...new Set([...KNOWN_SUITE_ORDER, ...Object.keys(rawTests)])]
    : [...KNOWN_SUITE_ORDER];

  return orderedKeys.reduce<Record<string, DashboardTestSuite>>((accumulator, suiteKey) => {
    const suite = rawTests?.[suiteKey];
    accumulator[suiteKey] = {
      passed: toPositiveNumber(suite?.passed),
      failed: toPositiveNumber(suite?.failed),
      total: toPositiveNumber(suite?.total),
      active: Boolean(suite?.active),
    };
    return accumulator;
  }, {});
}

export function normalizeSnapshot(raw: RawDashboardPayload): DashboardSnapshot {
  const activeLoop = normalizeActiveLoop(raw.loop?.active_loop);
  const researchMode = normalizeResearchMode(raw.loop?.research_mode ?? null);
  const currentAgent = normalizeAgent(raw.pipeline?.current_agent, activeLoop, researchMode);
  const tasks = (raw.tasks ?? []).map((task) => normalizeTask(task, activeLoop, researchMode));

  return {
    timestamp: raw.timestamp ?? null,
    runId: raw.run_id ?? null,
    elapsedSeconds: toPositiveNumber(raw.elapsed_seconds),
    loop: {
      activeLoop,
      researchMode,
    },
    pipeline: {
      currentAgent,
      rawAgent: raw.pipeline?.current_agent ?? null,
      currentTaskIndex: toPositiveNumber(raw.pipeline?.current_task_index),
      totalTasks: toPositiveNumber(raw.pipeline?.total_tasks),
      agentStartedAt: raw.pipeline?.agent_started_at ?? null,
    },
    tasks,
    metrics: {
      tokensIn: toPositiveNumber(raw.metrics?.tokens_in),
      tokensOut: toPositiveNumber(raw.metrics?.tokens_out),
      cachedTokens: toPositiveNumber(raw.metrics?.cached_tokens),
      currentModel: raw.metrics?.current_model ?? null,
      cycleNumber: raw.metrics?.cycle_number == null ? null : toPositiveNumber(raw.metrics.cycle_number),
    },
    tests: normalizeTestSuites(raw.tests),
    latestCommit: {
      hash: raw.latest_commit?.hash?.trim() ?? '',
      message: raw.latest_commit?.message?.trim() ?? '',
      timestamp: raw.latest_commit?.timestamp ?? null,
    },
    logLines: (raw.log_lines ?? []).filter((line): line is string => typeof line === 'string' && line.trim().length > 0),
  };
}

export function getActiveTask(snapshot: DashboardSnapshot): DashboardTask | null {
  return (
    snapshot.tasks.find((task) => task.status === 'active') ??
    snapshot.tasks[Math.max(0, snapshot.pipeline.currentTaskIndex - 1)] ??
    null
  );
}

export function getCompletedTaskCount(snapshot: DashboardSnapshot): number {
  const completedFromTasks = snapshot.tasks.filter((task) => task.status === 'complete').length;
  const completedFromCounter = snapshot.pipeline.currentTaskIndex > 0 ? snapshot.pipeline.currentTaskIndex - 1 : 0;
  const totalTasks = snapshot.pipeline.totalTasks;
  return Math.min(totalTasks || Number.MAX_SAFE_INTEGER, Math.max(completedFromTasks, completedFromCounter));
}

export function getProgressBreakdown(snapshot: DashboardSnapshot): { done: number; active: number; pending: number } {
  const totalTasks = snapshot.pipeline.totalTasks;
  const done = getCompletedTaskCount(snapshot);
  const active = totalTasks > 0 && snapshot.pipeline.currentTaskIndex > 0 ? 1 : 0;
  const pending = Math.max(0, totalTasks - done - active);
  return { done, active, pending };
}

export function mergeLogLines(previousLines: string[], nextLines: string[]): { lines: string[]; appended: boolean } {
  if (!nextLines.length) {
    return { lines: previousLines, appended: false };
  }

  const maxOverlap = Math.min(previousLines.length, nextLines.length);
  for (let overlap = maxOverlap; overlap >= 0; overlap -= 1) {
    const previousTail = previousLines.slice(previousLines.length - overlap);
    const nextHead = nextLines.slice(0, overlap);
    if (JSON.stringify(previousTail) === JSON.stringify(nextHead)) {
      const merged = previousLines.concat(nextLines.slice(overlap)).slice(-80);
      return {
        lines: merged,
        appended: nextLines.length > overlap,
      };
    }
  }

  return {
    lines: nextLines.slice(-80),
    appended: true,
  };
}

export function createIdleSnapshot(): DashboardSnapshot {
  return structuredClone(IDLE_SNAPSHOT);
}

export function getActiveStage(snapshot: DashboardSnapshot): ReturnType<typeof getPipelineStageForAgent> {
  return getPipelineStageForAgent(snapshot.pipeline.currentAgent as CanonicalAgent | null);
}
