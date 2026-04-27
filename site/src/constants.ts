import type { DashboardSnapshot, PipelineStage } from './types.js';

export const COLORS = {
  background: '#090d10',
  surface: '#11171d',
  surfaceRaised: '#161d24',
  border: '#28313a',
  muted: '#767267',
  textPrimary: '#ddd6c4',
  textSecondary: '#a7a092',
  signal: '#4ee0cf',
  signalDim: '#245f59',
  amber: '#c5a15b',
  green: '#7bbf84',
};

export const EXECUTION_STAGES: PipelineStage[] = [
  'builder',
  'checker',
  'fixer',
  'doublechecker',
  'updater',
  'troubleshooter',
  'consultant',
];

export const PLANNING_STAGES: PipelineStage[] = [
  'planner',
  'manager',
  'mechanic',
  'auditor',
  'arbiter',
];

export const LEARNING_STAGES: PipelineStage[] = [
  'analyst',
  'professor',
  'curator',
];

export const PIPELINE_STAGES: PipelineStage[] = EXECUTION_STAGES;

export const KNOWN_SUITE_ORDER = ['runtime', 'queue', 'closure', 'site'];

export const IDLE_SNAPSHOT: DashboardSnapshot = {
  timestamp: null,
  runId: null,
  elapsedSeconds: 0,
  tracker: {
    syncMode: 'unknown',
    heartbeatSeconds: null,
    debounceSeconds: null,
  },
  loop: {
    activeLoop: 'execution',
    researchMode: null,
  },
  pipeline: {
    currentAgent: null,
    rawAgent: null,
    currentTaskIndex: 0,
    totalTasks: 0,
    agentStartedAt: null,
  },
  tasks: [],
  metrics: {
    tokensIn: 0,
    tokensOut: 0,
    cachedTokens: 0,
    currentModel: null,
    cycleNumber: null,
  },
  tests: {
    runtime: { passed: 0, failed: 0, total: 0, active: false },
    queue: { passed: 0, failed: 0, total: 0, active: false },
    closure: { passed: 0, failed: 0, total: 0, active: false },
    site: { passed: 0, failed: 0, total: 0, active: false },
  },
  queues: {
    execution: { queue: 0, active: 0, done: 0, blocked: 0 },
    planning: { queue: 0, active: 0, done: 0, blocked: 0 },
    learning: { queue: 0, active: 0, done: 0, blocked: 0 },
  },
  runtime: {
    workspace: null,
    runtimeMode: null,
    processRunning: false,
    paused: false,
    stopRequested: false,
    activeModeId: null,
    compiledPlanId: null,
    compiledPlanCurrentness: null,
    activePlane: 'execution',
    activeStage: null,
    activeRunId: null,
    activeWorkItemKind: null,
    activeWorkItemId: null,
    statusMarkers: {
      execution: null,
      planning: null,
      learning: null,
    },
    currentFailureClass: null,
    watcherMode: null,
    baselineSeedPackageVersion: null,
    closure: {
      openCount: 0,
      rootSpecId: null,
      blockedByLineageWork: false,
      latestVerdictPath: null,
      latestReportPath: null,
    },
  },
  latestCommit: {
    hash: '',
    message: '',
    timestamp: null,
  },
  logLines: ['[--:--:--] Awaiting Millrace runtime snapshot...'],
};
