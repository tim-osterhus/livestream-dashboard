import type { DashboardSnapshot, PipelineStage } from './types.js';

export const COLORS = {
  background: '#222B31',
  surface: '#2A353D',
  muted: '#55666E',
  textPrimary: '#D0D0D0',
  textSecondary: '#888888',
  heatEmber: '#440101',
  heatHot: '#C7080C',
  heatBlazing: '#E22227',
  amber: '#8B6914',
};

export const PIPELINE_STAGES: PipelineStage[] = [
  'research',
  'decompose',
  'builder',
  'integrate',
  'qa',
  'hotfix',
  'doublecheck',
  'finalize',
];

export const KNOWN_SUITE_ORDER = ['gcc_torture', 'sqlite', 'redis', 'lua'];

export const IDLE_SNAPSHOT: DashboardSnapshot = {
  timestamp: null,
  runId: null,
  elapsedSeconds: 0,
  loop: {
    activeLoop: 'orchestration',
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
    gcc_torture: { passed: 0, failed: 0, total: 0, active: false },
    sqlite: { passed: 0, failed: 0, total: 0, active: false },
    redis: { passed: 0, failed: 0, total: 0, active: false },
    lua: { passed: 0, failed: 0, total: 0, active: false },
  },
  latestCommit: {
    hash: '',
    message: '',
    timestamp: null,
  },
  logLines: ['[--:--:--] Awaiting orchestration start...'],
};
