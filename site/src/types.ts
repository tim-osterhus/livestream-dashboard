export type ActiveLoop = 'execution' | 'planning' | 'learning';
export type ResearchMode = 'goalspec' | 'incident' | 'audit' | null;

export type CanonicalAgent =
  | 'builder'
  | 'checker'
  | 'fixer'
  | 'doublechecker'
  | 'updater'
  | 'troubleshooter'
  | 'consultant'
  | 'planner'
  | 'manager'
  | 'mechanic'
  | 'auditor'
  | 'arbiter'
  | 'analyst'
  | 'professor'
  | 'curator';

export type PipelineStage =
  | 'builder'
  | 'checker'
  | 'fixer'
  | 'doublechecker'
  | 'updater'
  | 'troubleshooter'
  | 'consultant'
  | 'planner'
  | 'manager'
  | 'mechanic'
  | 'auditor'
  | 'arbiter'
  | 'analyst'
  | 'professor'
  | 'curator';

export interface RawTask {
  id?: number | string;
  name?: string;
  status?: string;
  active_agent?: string | null;
}

export interface RawTestSuite {
  passed?: number;
  failed?: number;
  total?: number;
  active?: boolean;
}

export interface RawDashboardPayload {
  timestamp?: string;
  run_id?: string;
  elapsed_seconds?: number;
  loop?: {
    active_loop?: string;
    research_mode?: string | null;
  };
  pipeline?: {
    current_agent?: string | null;
    current_task_index?: number;
    total_tasks?: number;
    agent_started_at?: string | null;
  };
  tasks?: RawTask[];
  metrics?: {
    tokens_in?: number;
    tokens_out?: number;
    cached_tokens?: number;
    current_model?: string | null;
    cycle_number?: number | string | null;
  };
  tests?: Record<string, RawTestSuite>;
  latest_commit?: {
    hash?: string;
    message?: string;
    timestamp?: string | null;
  };
  log_lines?: string[];
  runtime?: {
    workspace?: string | null;
    runtime_mode?: string | null;
    process_running?: boolean;
    paused?: boolean;
    stop_requested?: boolean;
    active_mode_id?: string | null;
    compiled_plan_id?: string | null;
    compiled_plan_currentness?: string | null;
    active_plane?: string | null;
    active_stage?: string | null;
    active_run_id?: string | null;
    active_work_item_kind?: string | null;
    active_work_item_id?: string | null;
    execution_status_marker?: string | null;
    planning_status_marker?: string | null;
    learning_status_marker?: string | null;
    current_failure_class?: string | null;
    watcher_mode?: string | null;
    baseline_seed_package_version?: string | null;
    closure?: {
      open_count?: number;
      root_spec_id?: string | null;
      blocked_by_lineage_work?: boolean;
      latest_verdict_path?: string | null;
      latest_report_path?: string | null;
    };
  };
  queues?: Partial<Record<ActiveLoop, RawQueueCounts>>;
}

export interface RawQueueCounts {
  queue?: number;
  active?: number;
  done?: number;
  blocked?: number;
  incoming?: number;
  resolved?: number;
}

export interface DashboardTask {
  id: number | string;
  name: string;
  status: 'complete' | 'active' | 'pending';
  activeAgent: CanonicalAgent | null;
}

export interface DashboardTestSuite {
  passed: number;
  failed: number;
  total: number;
  active: boolean;
}

export interface DashboardQueueCounts {
  queue: number;
  active: number;
  done: number;
  blocked: number;
}

export interface DashboardRuntime {
  workspace: string | null;
  runtimeMode: string | null;
  processRunning: boolean;
  paused: boolean;
  stopRequested: boolean;
  activeModeId: string | null;
  compiledPlanId: string | null;
  compiledPlanCurrentness: string | null;
  activePlane: ActiveLoop;
  activeStage: CanonicalAgent | null;
  activeRunId: string | null;
  activeWorkItemKind: string | null;
  activeWorkItemId: string | null;
  statusMarkers: Record<ActiveLoop, string | null>;
  currentFailureClass: string | null;
  watcherMode: string | null;
  baselineSeedPackageVersion: string | null;
  closure: {
    openCount: number;
    rootSpecId: string | null;
    blockedByLineageWork: boolean;
    latestVerdictPath: string | null;
    latestReportPath: string | null;
  };
}

export interface DashboardSnapshot {
  timestamp: string | null;
  runId: string | null;
  elapsedSeconds: number;
  loop: {
    activeLoop: ActiveLoop;
    researchMode: ResearchMode;
  };
  pipeline: {
    currentAgent: CanonicalAgent | null;
    rawAgent: string | null;
    currentTaskIndex: number;
    totalTasks: number;
    agentStartedAt: string | null;
  };
  tasks: DashboardTask[];
  metrics: {
    tokensIn: number;
    tokensOut: number;
    cachedTokens: number;
    currentModel: string | null;
    cycleNumber: number | null;
  };
  tests: Record<string, DashboardTestSuite>;
  queues: Record<ActiveLoop, DashboardQueueCounts>;
  runtime: DashboardRuntime;
  latestCommit: {
    hash: string;
    message: string;
    timestamp: string | null;
  };
  logLines: string[];
}

export interface WorkerDefinition {
  id: CanonicalAgent;
  displayName: string;
  color: string;
}

export interface RuntimeConfig {
  r2Endpoint?: string;
  pollIntervalMs?: number;
  mockMode?: string;
  useMockWhenEndpointMissing?: boolean;
  staleAfterConsecutiveUnchangedPolls?: number;
}

export interface ResolvedConfig {
  endpoint: string | null;
  fallbackEndpoint: string | null;
  endpointLabel: string;
  pollIntervalMs: number;
  staleAfterConsecutiveUnchangedPolls: number;
}
