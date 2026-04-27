import { IDLE_SNAPSHOT, KNOWN_SUITE_ORDER } from '../constants.js';
import type {
  ActiveLoop,
  CanonicalAgent,
  DashboardQueueCounts,
  DashboardRuntime,
  DashboardSnapshot,
  DashboardTask,
  DashboardTestSuite,
  RawDashboardPayload,
  RawQueueCounts,
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

function normalizeActiveLoop(value: string | null | undefined): ActiveLoop {
  const normalized = value?.toLowerCase().replace(/[\s-]+/g, '_');
  if (normalized === 'planning' || normalized === 'research') {
    return 'planning';
  }
  if (normalized === 'learning') {
    return 'learning';
  }
  return 'execution';
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

function normalizeQueueCounts(rawCounts: RawQueueCounts | undefined): DashboardQueueCounts {
  return {
    queue: toPositiveNumber(rawCounts?.queue ?? rawCounts?.incoming),
    active: toPositiveNumber(rawCounts?.active),
    done: toPositiveNumber(rawCounts?.done ?? rawCounts?.resolved),
    blocked: toPositiveNumber(rawCounts?.blocked),
  };
}

function normalizeQueues(rawQueues: RawDashboardPayload['queues']): DashboardSnapshot['queues'] {
  return {
    execution: normalizeQueueCounts(rawQueues?.execution),
    planning: normalizeQueueCounts(rawQueues?.planning),
    learning: normalizeQueueCounts(rawQueues?.learning),
  };
}

function normalizeRuntime(
  raw: RawDashboardPayload,
  activeLoop: ActiveLoop,
  researchMode: DashboardSnapshot['loop']['researchMode'],
): DashboardRuntime {
  const runtime = raw.runtime;
  const runtimePlane = normalizeActiveLoop(runtime?.active_plane ?? raw.loop?.active_loop);
  return {
    workspace: runtime?.workspace ?? null,
    runtimeMode: runtime?.runtime_mode ?? null,
    processRunning: Boolean(runtime?.process_running),
    paused: Boolean(runtime?.paused),
    stopRequested: Boolean(runtime?.stop_requested),
    activeModeId: runtime?.active_mode_id ?? null,
    compiledPlanId: runtime?.compiled_plan_id ?? null,
    compiledPlanCurrentness: runtime?.compiled_plan_currentness ?? null,
    activePlane: runtimePlane || activeLoop,
    activeStage: normalizeAgent(runtime?.active_stage ?? raw.pipeline?.current_agent, activeLoop, researchMode),
    activeRunId: runtime?.active_run_id ?? null,
    activeWorkItemKind: runtime?.active_work_item_kind ?? null,
    activeWorkItemId: runtime?.active_work_item_id ?? null,
    statusMarkers: {
      execution: runtime?.execution_status_marker ?? null,
      planning: runtime?.planning_status_marker ?? null,
      learning: runtime?.learning_status_marker ?? null,
    },
    currentFailureClass: runtime?.current_failure_class ?? null,
    watcherMode: runtime?.watcher_mode ?? null,
    baselineSeedPackageVersion: runtime?.baseline_seed_package_version ?? null,
    closure: {
      openCount: toPositiveNumber(runtime?.closure?.open_count),
      rootSpecId: runtime?.closure?.root_spec_id ?? null,
      blockedByLineageWork: Boolean(runtime?.closure?.blocked_by_lineage_work),
      latestVerdictPath: runtime?.closure?.latest_verdict_path ?? null,
      latestReportPath: runtime?.closure?.latest_report_path ?? null,
    },
  };
}

export function normalizeSnapshot(raw: RawDashboardPayload): DashboardSnapshot {
  const activeLoop = normalizeActiveLoop(raw.runtime?.active_plane ?? raw.loop?.active_loop);
  const researchMode = normalizeResearchMode(raw.loop?.research_mode ?? null);
  const currentAgent = normalizeAgent(raw.pipeline?.current_agent, activeLoop, researchMode);
  const tasks = (raw.tasks ?? []).map((task) => normalizeTask(task, activeLoop, researchMode));
  const runtime = normalizeRuntime(raw, activeLoop, researchMode);

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
    queues: normalizeQueues(raw.queues),
    runtime,
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
  if (snapshot.tasks.length) {
    return completedFromTasks;
  }
  const completedFromCounter = snapshot.pipeline.currentTaskIndex > 0 ? snapshot.pipeline.currentTaskIndex - 1 : 0;
  const totalTasks = snapshot.pipeline.totalTasks;
  return Math.min(totalTasks || Number.MAX_SAFE_INTEGER, Math.max(completedFromTasks, completedFromCounter));
}

export function getProgressBreakdown(snapshot: DashboardSnapshot): { done: number; active: number; pending: number } {
  if (snapshot.tasks.length) {
    return {
      done: snapshot.tasks.filter((task) => task.status === 'complete').length,
      active: snapshot.tasks.filter((task) => task.status === 'active').length,
      pending: snapshot.tasks.filter((task) => task.status === 'pending').length,
    };
  }

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
  return getPipelineStageForAgent((snapshot.runtime.activeStage ?? snapshot.pipeline.currentAgent) as CanonicalAgent | null);
}
