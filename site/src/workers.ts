import type { ActiveLoop, CanonicalAgent, PipelineStage, ResearchMode, WorkerDefinition } from './types.js';

export const ORCHESTRATION_WORKERS: WorkerDefinition[] = [
  { id: 'start', displayName: 'Builder', color: '#6B3D3D' },
  { id: 'integrate', displayName: 'Integrator', color: '#3D5A6B' },
  { id: 'check', displayName: 'QA', color: '#5A5A3D' },
  { id: 'hotfix', displayName: 'Hotfix', color: '#4A6B3D' },
  { id: 'doublecheck', displayName: 'Doublecheck', color: '#3D4A5A' },
  { id: 'consult', displayName: 'Consult', color: '#6B3D5A' },
  { id: 'troubleshoot', displayName: 'Troubleshoot', color: '#5A3D4A' },
  { id: 'update', displayName: 'Update', color: '#6B5A4A' },
];

const GOALSPEC_WORKERS: WorkerDefinition[] = [
  { id: 'goal_intake', displayName: 'Goal Intake', color: '#42526B' },
  { id: 'spec_synthesis', displayName: 'Spec Synthesis', color: '#3D6670' },
  { id: 'spec_review', displayName: 'Spec Review', color: '#4F5E8C' },
  { id: 'critic', displayName: 'Critic', color: '#6A4C7D' },
  { id: 'designer', displayName: 'Designer', color: '#5A6A83' },
  { id: 'taskmaster', displayName: 'Taskmaster', color: '#486E74' },
  { id: 'taskaudit', displayName: 'Task Audit', color: '#64738A' },
  { id: 'objective_profile_sync', displayName: 'Objective Sync', color: '#43627A' },
  { id: 'mechanic', displayName: 'Mechanic', color: '#4E5A68' },
];

const INCIDENT_WORKERS: WorkerDefinition[] = [
  { id: 'incident_intake', displayName: 'Incident Intake', color: '#48647B' },
  { id: 'incident_resolve', displayName: 'Incident Resolve', color: '#4F5C84' },
  { id: 'incident_archive', displayName: 'Incident Archive', color: '#526C78' },
  { id: 'taskmaster', displayName: 'Taskmaster', color: '#486E74' },
  { id: 'taskaudit', displayName: 'Task Audit', color: '#64738A' },
  { id: 'mechanic', displayName: 'Mechanic', color: '#4E5A68' },
];

const AUDIT_WORKERS: WorkerDefinition[] = [
  { id: 'contractor', displayName: 'Contractor', color: '#5A6078' },
  { id: 'audit_intake', displayName: 'Audit Intake', color: '#3E6077' },
  { id: 'audit_validate', displayName: 'Audit Validate', color: '#55718B' },
  { id: 'audit_gatekeeper', displayName: 'Audit Gatekeeper', color: '#5D4C79' },
  { id: 'objective_profile_sync', displayName: 'Objective Sync', color: '#43627A' },
  { id: 'mechanic', displayName: 'Mechanic', color: '#4E5A68' },
];

export const WORKER_DEFINITIONS: Record<CanonicalAgent, WorkerDefinition> = {
  start: ORCHESTRATION_WORKERS[0],
  integrate: ORCHESTRATION_WORKERS[1],
  check: ORCHESTRATION_WORKERS[2],
  hotfix: ORCHESTRATION_WORKERS[3],
  doublecheck: ORCHESTRATION_WORKERS[4],
  consult: ORCHESTRATION_WORKERS[5],
  troubleshoot: ORCHESTRATION_WORKERS[6],
  update: ORCHESTRATION_WORKERS[7],
  goal_intake: GOALSPEC_WORKERS[0],
  spec_synthesis: GOALSPEC_WORKERS[1],
  spec_review: GOALSPEC_WORKERS[2],
  critic: GOALSPEC_WORKERS[3],
  designer: GOALSPEC_WORKERS[4],
  taskmaster: GOALSPEC_WORKERS[5],
  taskaudit: GOALSPEC_WORKERS[6],
  objective_profile_sync: GOALSPEC_WORKERS[7],
  mechanic: GOALSPEC_WORKERS[8],
  incident_intake: INCIDENT_WORKERS[0],
  incident_resolve: INCIDENT_WORKERS[1],
  incident_archive: INCIDENT_WORKERS[2],
  contractor: AUDIT_WORKERS[0],
  audit_intake: AUDIT_WORKERS[1],
  audit_validate: AUDIT_WORKERS[2],
  audit_gatekeeper: AUDIT_WORKERS[3],
};

const AGENT_STAGE_MAP: Record<CanonicalAgent, PipelineStage> = {
  goal_intake: 'research',
  spec_synthesis: 'research',
  spec_review: 'research',
  critic: 'research',
  designer: 'research',
  objective_profile_sync: 'research',
  mechanic: 'research',
  incident_intake: 'research',
  incident_resolve: 'research',
  incident_archive: 'research',
  contractor: 'research',
  audit_intake: 'research',
  audit_validate: 'research',
  audit_gatekeeper: 'research',
  taskmaster: 'decompose',
  taskaudit: 'decompose',
  start: 'builder',
  integrate: 'integrate',
  check: 'qa',
  hotfix: 'hotfix',
  troubleshoot: 'hotfix',
  doublecheck: 'doublecheck',
  consult: 'finalize',
  update: 'finalize',
};

const KNOWN_AGENT_SET = new Set<CanonicalAgent>(Object.keys(WORKER_DEFINITIONS) as CanonicalAgent[]);

const AGENT_ALIASES: Record<string, CanonicalAgent> = {
  builder: 'start',
  build: 'start',
  start_large_plan: 'start',
  start_large_execute: 'start',
  refactor: 'start',
  reassess: 'start',
  integrator: 'integrate',
  integration: 'integrate',
  qa: 'check',
  qa_plan: 'check',
  qa_execute: 'check',
  checker: 'check',
  double_check: 'doublecheck',
  doublecheck_qa: 'doublecheck',
  trouble: 'troubleshoot',
  goalintake: 'goal_intake',
  articulate: 'goal_intake',
  analyze: 'spec_synthesis',
  clarify: 'spec_review',
  objective_sync: 'objective_profile_sync',
  sync: 'objective_profile_sync',
  auditgatekeeper: 'audit_gatekeeper',
};

export function normalizeResearchMode(value: string | null | undefined): ResearchMode {
  if (!value) {
    return null;
  }

  const normalized = value.toLowerCase().replace(/[\s-]+/g, '_');
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

  if (token.includes('build')) {
    return 'start';
  }
  if (token.includes('integrat')) {
    return 'integrate';
  }
  if (token === 'qa' || token.includes('check')) {
    return token.includes('double') ? 'doublecheck' : 'check';
  }
  if (token.includes('double')) {
    return 'doublecheck';
  }
  if (token.includes('hotfix')) {
    return 'hotfix';
  }
  if (token.includes('troubleshoot')) {
    return 'troubleshoot';
  }
  if (token.includes('consult')) {
    return 'consult';
  }
  if (token.includes('update')) {
    return 'update';
  }

  if (activeLoop === 'research') {
    if (token.includes('goal')) {
      return 'goal_intake';
    }
    if (token.includes('synth')) {
      return 'spec_synthesis';
    }
    if (token.includes('review')) {
      return 'spec_review';
    }
    if (token.includes('critic')) {
      return 'critic';
    }
    if (token.includes('design')) {
      return 'designer';
    }
    if (token.includes('taskmaster')) {
      return 'taskmaster';
    }
    if (token.includes('taskaudit')) {
      return 'taskaudit';
    }
    if (token.includes('objective') || token.includes('profile')) {
      return 'objective_profile_sync';
    }
    if (token.includes('mechanic')) {
      return 'mechanic';
    }
    if (token.includes('incident')) {
      if (token.includes('archive')) return 'incident_archive';
      if (token.includes('resolve')) return 'incident_resolve';
      return 'incident_intake';
    }
    if (token.includes('contract')) {
      return 'contractor';
    }
    if (token.includes('audit')) {
      if (token.includes('gate')) return 'audit_gatekeeper';
      if (token.includes('valid')) return 'audit_validate';
      return 'audit_intake';
    }

    if (researchMode === 'incident') {
      return 'incident_intake';
    }
    if (researchMode === 'audit') {
      return 'audit_intake';
    }
    return 'goal_intake';
  }

  return null;
}

export function getDisplayName(agent: CanonicalAgent | null, fallback = '--'): string {
  if (!agent) {
    return fallback;
  }
  return WORKER_DEFINITIONS[agent]?.displayName ?? fallback;
}

export function getWorkerEnsemble(loop: ActiveLoop, researchMode: ResearchMode): WorkerDefinition[] {
  if (loop === 'orchestration') {
    return ORCHESTRATION_WORKERS;
  }

  if (researchMode === 'incident') {
    return INCIDENT_WORKERS;
  }

  if (researchMode === 'audit') {
    return AUDIT_WORKERS;
  }

  return GOALSPEC_WORKERS;
}

export function getPipelineStageForAgent(agent: CanonicalAgent | null): PipelineStage | null {
  if (!agent) {
    return null;
  }
  return AGENT_STAGE_MAP[agent] ?? null;
}
