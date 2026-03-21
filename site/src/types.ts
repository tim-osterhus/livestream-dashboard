export type ActiveLoop = 'orchestration' | 'research';
export type ResearchMode = 'goalspec' | 'incident' | 'audit' | null;

export type CanonicalAgent =
  | 'start'
  | 'integrate'
  | 'check'
  | 'hotfix'
  | 'doublecheck'
  | 'consult'
  | 'troubleshoot'
  | 'update'
  | 'goal_intake'
  | 'spec_synthesis'
  | 'spec_review'
  | 'critic'
  | 'designer'
  | 'taskmaster'
  | 'taskaudit'
  | 'objective_profile_sync'
  | 'mechanic'
  | 'incident_intake'
  | 'incident_resolve'
  | 'incident_archive'
  | 'contractor'
  | 'audit_intake'
  | 'audit_validate'
  | 'audit_gatekeeper';

export type PipelineStage =
  | 'research'
  | 'decompose'
  | 'builder'
  | 'integrate'
  | 'qa'
  | 'hotfix'
  | 'doublecheck'
  | 'finalize';

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
    currentModel: string | null;
    cycleNumber: number | null;
  };
  tests: Record<string, DashboardTestSuite>;
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
