import { EXECUTION_STAGES, LEARNING_STAGES, PLANNING_STAGES } from './constants.js';
import type { ActiveLoop, CanonicalAgent, PipelineStage, ResearchMode, WorkerDefinition } from './types.js';

export const EXECUTION_WORKERS: WorkerDefinition[] = [
  { id: 'builder', displayName: 'Builder', color: '#4ee0cf' },
  { id: 'checker', displayName: 'Checker', color: '#8fb7ff' },
  { id: 'fixer', displayName: 'Fixer', color: '#c5a15b' },
  { id: 'doublechecker', displayName: 'Doublechecker', color: '#7bbf84' },
  { id: 'updater', displayName: 'Updater', color: '#ddd6c4' },
  { id: 'troubleshooter', displayName: 'Troubleshooter', color: '#d87878' },
  { id: 'consultant', displayName: 'Consultant', color: '#b494d6' },
];

export const PLANNING_WORKERS: WorkerDefinition[] = [
  { id: 'planner', displayName: 'Planner', color: '#4ee0cf' },
  { id: 'manager', displayName: 'Manager', color: '#8fb7ff' },
  { id: 'mechanic', displayName: 'Mechanic', color: '#c5a15b' },
  { id: 'auditor', displayName: 'Auditor', color: '#7bbf84' },
  { id: 'arbiter', displayName: 'Arbiter', color: '#ddd6c4' },
];

export const LEARNING_WORKERS: WorkerDefinition[] = [
  { id: 'analyst', displayName: 'Analyst', color: '#4ee0cf' },
  { id: 'professor', displayName: 'Professor', color: '#8fb7ff' },
  { id: 'curator', displayName: 'Curator', color: '#c5a15b' },
];

export const WORKER_DEFINITIONS: Record<CanonicalAgent, WorkerDefinition> = {
  builder: EXECUTION_WORKERS[0],
  checker: EXECUTION_WORKERS[1],
  fixer: EXECUTION_WORKERS[2],
  doublechecker: EXECUTION_WORKERS[3],
  updater: EXECUTION_WORKERS[4],
  troubleshooter: EXECUTION_WORKERS[5],
  consultant: EXECUTION_WORKERS[6],
  planner: PLANNING_WORKERS[0],
  manager: PLANNING_WORKERS[1],
  mechanic: PLANNING_WORKERS[2],
  auditor: PLANNING_WORKERS[3],
  arbiter: PLANNING_WORKERS[4],
  analyst: LEARNING_WORKERS[0],
  professor: LEARNING_WORKERS[1],
  curator: LEARNING_WORKERS[2],
};

const AGENT_STAGE_MAP: Record<CanonicalAgent, PipelineStage> = {
  builder: 'builder',
  checker: 'checker',
  fixer: 'fixer',
  doublechecker: 'doublechecker',
  updater: 'updater',
  troubleshooter: 'troubleshooter',
  consultant: 'consultant',
  planner: 'planner',
  manager: 'manager',
  mechanic: 'mechanic',
  auditor: 'auditor',
  arbiter: 'arbiter',
  analyst: 'analyst',
  professor: 'professor',
  curator: 'curator',
};

const KNOWN_AGENT_SET = new Set<CanonicalAgent>(Object.keys(WORKER_DEFINITIONS) as CanonicalAgent[]);

const AGENT_ALIASES: Record<string, CanonicalAgent> = {
  start: 'builder',
  build: 'builder',
  builder: 'builder',
  integrator: 'builder',
  integrate: 'builder',
  start_large_plan: 'builder',
  start_large_execute: 'builder',
  refactor: 'builder',
  reassess: 'builder',
  qa: 'checker',
  check: 'checker',
  checker: 'checker',
  qa_plan: 'checker',
  qa_execute: 'checker',
  hotfix: 'fixer',
  fix: 'fixer',
  fixer: 'fixer',
  doublecheck: 'doublechecker',
  double_check: 'doublechecker',
  doublecheck_qa: 'doublechecker',
  update: 'updater',
  updater: 'updater',
  trouble: 'troubleshooter',
  troubleshoot: 'troubleshooter',
  consult: 'consultant',
  consultant: 'consultant',
  goal_intake: 'planner',
  goalintake: 'planner',
  goalspec: 'planner',
  articulate: 'planner',
  spec_synthesis: 'manager',
  analyze: 'manager',
  designer: 'manager',
  critic: 'auditor',
  spec_review: 'auditor',
  clarify: 'auditor',
  taskmaster: 'manager',
  taskaudit: 'auditor',
  objective_profile_sync: 'manager',
  objective_sync: 'manager',
  incident_intake: 'manager',
  incident_resolve: 'mechanic',
  incident_archive: 'auditor',
  contractor: 'manager',
  audit_intake: 'auditor',
  audit_validate: 'auditor',
  audit_gatekeeper: 'arbiter',
  auditgatekeeper: 'arbiter',
};

export function normalizeResearchMode(value: string | null | undefined): ResearchMode {
  if (!value) {
    return null;
  }

  const normalized = normalizeToken(value);
  if (normalized === 'goalspec' || normalized === 'goal_spec') {
    return 'goalspec';
  }
  if (normalized === 'incident' || normalized === 'incidents') {
    return 'incident';
  }
  if (normalized === 'audit') {
    return 'audit';
  }
  return null;
}

function normalizeToken(value: string): string {
  return value.toLowerCase().trim().replace(/[\s-]+/g, '_');
}

export function normalizeAgent(
  rawAgent: string | null | undefined,
  activeLoop: ActiveLoop,
  researchMode: ResearchMode,
): CanonicalAgent | null {
  if (!rawAgent) {
    return null;
  }

  const token = normalizeToken(rawAgent);
  if (KNOWN_AGENT_SET.has(token as CanonicalAgent)) {
    return token as CanonicalAgent;
  }

  if (AGENT_ALIASES[token]) {
    return AGENT_ALIASES[token];
  }

  if (token.includes('double')) {
    return 'doublechecker';
  }
  if (token.includes('check') || token === 'qa') {
    return 'checker';
  }
  if (token.includes('fix') || token.includes('hotfix')) {
    return 'fixer';
  }
  if (token.includes('troubleshoot')) {
    return 'troubleshooter';
  }
  if (token.includes('consult')) {
    return 'consultant';
  }
  if (token.includes('update')) {
    return 'updater';
  }
  if (token.includes('build') || token.includes('integrat')) {
    return 'builder';
  }

  if (activeLoop === 'planning') {
    if (token.includes('arbiter') || token.includes('gate')) {
      return 'arbiter';
    }
    if (token.includes('audit') || token.includes('review') || token.includes('critic')) {
      return 'auditor';
    }
    if (token.includes('mechanic') || token.includes('resolve')) {
      return 'mechanic';
    }
    if (token.includes('manager') || token.includes('task') || token.includes('synth')) {
      return 'manager';
    }
    if (researchMode === 'audit') {
      return 'auditor';
    }
    if (researchMode === 'incident') {
      return 'mechanic';
    }
    return 'planner';
  }

  if (activeLoop === 'learning') {
    if (token.includes('professor')) {
      return 'professor';
    }
    if (token.includes('curator')) {
      return 'curator';
    }
    return 'analyst';
  }

  return null;
}

export function getDisplayName(agent: CanonicalAgent | null, fallback = '--'): string {
  if (!agent) {
    return fallback;
  }
  return WORKER_DEFINITIONS[agent]?.displayName ?? fallback;
}

export function getWorkerEnsemble(loop: ActiveLoop, _researchMode: ResearchMode): WorkerDefinition[] {
  if (loop === 'planning') {
    return PLANNING_WORKERS;
  }
  if (loop === 'learning') {
    return LEARNING_WORKERS;
  }
  return EXECUTION_WORKERS;
}

export function getStageSequence(loop: ActiveLoop): PipelineStage[] {
  if (loop === 'planning') {
    return PLANNING_STAGES;
  }
  if (loop === 'learning') {
    return LEARNING_STAGES;
  }
  return EXECUTION_STAGES;
}

export function getPipelineStageForAgent(agent: CanonicalAgent | null): PipelineStage | null {
  if (!agent) {
    return null;
  }
  return AGENT_STAGE_MAP[agent] ?? null;
}
