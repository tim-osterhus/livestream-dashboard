import { React, useEffect, useMemo, useRef, useState } from '../react-global.js';
import { PIPELINE_STAGES } from '../constants.js';
import type {
  CanonicalAgent,
  DashboardSnapshot,
  DashboardTask,
  DashboardTestSuite,
  PipelineStage,
  WorkerDefinition,
} from '../types.js';
import { formatElapsedTime, prettifySuiteName, truncateMiddle } from '../utils/format.js';
import { getActiveStage, getActiveTask, getCompletedTaskCount, getProgressBreakdown } from '../utils/telemetry.js';
import { getDisplayName, getWorkerEnsemble } from '../workers.js';

interface WorkshopSceneProps {
  snapshot: DashboardSnapshot;
  previousAgent: CanonicalAgent | null;
}

function formatStageLabel(stage: PipelineStage | null): string {
  if (!stage) {
    return 'Awaiting stage';
  }

  switch (stage) {
    case 'qa':
      return 'QA';
    default:
      return stage.replace(/_/g, ' ');
  }
}

function formatLoopLabel(snapshot: DashboardSnapshot): string {
  if (snapshot.loop.activeLoop === 'research') {
    const mode = snapshot.loop.researchMode || 'goalspec';
    return `Research / ${mode}`;
  }
  return 'Orchestration / Forge';
}

function getFocusTitle(snapshot: DashboardSnapshot, activeTask: DashboardTask | null): string {
  if (!snapshot.pipeline.currentAgent && snapshot.pipeline.totalTasks === 0) {
    return 'Waiting for first loop signal';
  }
  if (activeTask?.name) {
    return activeTask.name;
  }
  if (snapshot.loop.activeLoop === 'research') {
    return 'Research loop is live';
  }
  return 'Awaiting next task card';
}

function getFocusTagline(snapshot: DashboardSnapshot): string {
  if (!snapshot.pipeline.currentAgent && snapshot.pipeline.totalTasks === 0) {
    return 'Start either logged loop and the dashboard will swap from seeded standby into live telemetry automatically.';
  }
  if (snapshot.loop.activeLoop === 'research') {
    return 'Use this surface to make decomposition, audit posture, and incident handling legible at a glance, not to mimic worker animation.';
  }
  return 'Execution is live. The center canvas should foreground task movement, verification evidence, and queue health instead of placeholder chrome.';
}

function getStageRuntimeSeconds(snapshot: DashboardSnapshot): number {
  if (!snapshot.pipeline.agentStartedAt || !snapshot.timestamp) {
    return 0;
  }

  const startedAtMs = Date.parse(snapshot.pipeline.agentStartedAt);
  const timestampMs = Date.parse(snapshot.timestamp);
  if (!Number.isFinite(startedAtMs) || !Number.isFinite(timestampMs)) {
    return 0;
  }

  return Math.max(0, Math.floor((timestampMs - startedAtMs) / 1000));
}

function getSuiteEntries(snapshot: DashboardSnapshot) {
  return Object.entries(snapshot.tests)
    .filter(([, suite]) => suite.active || suite.total > 0 || suite.passed > 0 || suite.failed > 0)
    .sort((left, right) => {
      const [leftName, leftSuite] = left;
      const [rightName, rightSuite] = right;
      const activeDiff = Number(rightSuite.active) - Number(leftSuite.active);
      if (activeDiff !== 0) {
        return activeDiff;
      }
      const totalDiff = rightSuite.total - leftSuite.total;
      if (totalDiff !== 0) {
        return totalDiff;
      }
      return leftName.localeCompare(rightName);
    });
}

function BackdropLayer({
  type,
  visible,
  pulsing,
}: {
  type: 'orchestration' | 'research';
  visible: boolean;
  pulsing: boolean;
}) {
  const isForge = type === 'orchestration';

  return (
    <div className={`scene-layer scene-layer--${type} ${visible ? 'scene-layer--visible' : ''} ${pulsing ? 'scene-layer--swap' : ''}`}>
      <div className={`scene-backdrop ${isForge ? 'scene-backdrop--forge' : 'scene-backdrop--study'}`} />
      <div className={`scene-atmosphere scene-atmosphere--${isForge ? 'forge' : 'study'}`} />
      <div className="scene-gridlines" />
      <div className="scene-wordmark">{isForge ? 'FORGE' : 'STUDY'}</div>
    </div>
  );
}

export function WorkshopScene({ snapshot, previousAgent }: WorkshopSceneProps) {
  const [completedAgent, setCompletedAgent] = useState(null as CanonicalAgent | null);
  const [researchSwapPulse, setResearchSwapPulse] = useState(false);
  const previousResearchModeRef = useRef(snapshot.loop.researchMode as DashboardSnapshot['loop']['researchMode']);

  useEffect(() => {
    if (!previousAgent) {
      return undefined;
    }

    setCompletedAgent(previousAgent);
    const timer = window.setTimeout(() => setCompletedAgent(null), 540);
    return () => window.clearTimeout(timer);
  }, [previousAgent]);

  useEffect(() => {
    const previousResearchMode = previousResearchModeRef.current;
    previousResearchModeRef.current = snapshot.loop.researchMode;

    if (previousResearchMode === snapshot.loop.researchMode) {
      return undefined;
    }

    setResearchSwapPulse(true);
    const timer = window.setTimeout(() => setResearchSwapPulse(false), 520);
    return () => window.clearTimeout(timer);
  }, [snapshot.loop.researchMode]);

  const workers = getWorkerEnsemble(snapshot.loop.activeLoop, snapshot.loop.researchMode);
  const activeTask = getActiveTask(snapshot);
  const activeStage = getActiveStage(snapshot);
  const progressBreakdown = getProgressBreakdown(snapshot);
  const completedTasks = useMemo(
    () => snapshot.tasks.filter((task) => task.status === 'complete').slice(-3).reverse(),
    [snapshot.tasks],
  );
  const upcomingTasks = useMemo(
    () => snapshot.tasks.filter((task) => task.status === 'pending').slice(0, 4),
    [snapshot.tasks],
  );
  const recentLogLines = useMemo(() => snapshot.logLines.slice(-4).reverse(), [snapshot.logLines]);
  const suiteEntries = useMemo(() => getSuiteEntries(snapshot).slice(0, 4), [snapshot]);
  const activeAgentName = getDisplayName(snapshot.pipeline.currentAgent);
  const stageRuntime = getStageRuntimeSeconds(snapshot);
  const totalCompletedTasks = getCompletedTaskCount(snapshot);
  const focusTitle = getFocusTitle(snapshot, activeTask);
  const focusTagline = getFocusTagline(snapshot);

  return (
    <section className="workshop-shell" aria-label="Mission control command deck">
      <BackdropLayer type="orchestration" visible={snapshot.loop.activeLoop === 'orchestration'} pulsing={false} />
      <BackdropLayer type="research" visible={snapshot.loop.activeLoop === 'research'} pulsing={researchSwapPulse} />

      <div className={`command-deck ${researchSwapPulse ? 'command-deck--swap' : ''}`}>
        <header className="command-deck__header">
          <div>
            <div className="command-deck__eyebrow">Millrace Mission Control</div>
            <div className="command-deck__title">Livestream dashboard</div>
          </div>
          <div className="command-deck__pills">
            <span className={`signal-pill signal-pill--${snapshot.loop.activeLoop}`}>{formatLoopLabel(snapshot)}</span>
            <span className="signal-pill signal-pill--neutral">{activeAgentName}</span>
            <span className="signal-pill signal-pill--neutral">{snapshot.runId || 'run-id pending'}</span>
          </div>
        </header>

        <div className="command-deck__body">
          <section className="deck-panel deck-panel--roster">
            <div className="deck-panel__heading">Agent Roster</div>
            <p className="deck-panel__hint">
              Track1 is intentionally skipped here. The roster stays compact so task flow, validation, and queue state can own the screen.
            </p>
            <div className="roster-list">
              {workers.map((worker: WorkerDefinition) => {
                const isActive = worker.id === snapshot.pipeline.currentAgent;
                const isCompleting = worker.id === completedAgent;
                const workerStage = formatStageLabel(getActiveStage({
                  ...snapshot,
                  pipeline: { ...snapshot.pipeline, currentAgent: worker.id },
                }));

                return (
                  <div
                    key={worker.id}
                    className={`roster-card ${isActive ? 'roster-card--active' : ''} ${isCompleting ? 'roster-card--handoff' : ''}`}
                  >
                    <div className="roster-card__swatch" style={{ background: worker.color }} />
                    <div className="roster-card__meta">
                      <div className="roster-card__name">{worker.displayName}</div>
                      <div className="roster-card__state">
                        {isActive ? 'Live now' : isCompleting ? 'Handoff' : 'Standby'}
                      </div>
                    </div>
                    <div className="roster-card__stage">{workerStage}</div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="deck-panel deck-panel--focus">
            <div className="focus-hero">
              <div className="focus-hero__eyebrow">{formatStageLabel(activeStage)}</div>
              <h2 className="focus-hero__task" title={focusTitle}>
                {focusTitle}
              </h2>
              <div className="focus-hero__subline">
                {focusTagline}
              </div>
            </div>

            <div className="focus-stats">
              <div className="focus-stat">
                <span className="focus-stat__label">Current task</span>
                <strong className="focus-stat__value">
                  {snapshot.pipeline.currentTaskIndex} / {snapshot.pipeline.totalTasks}
                </strong>
              </div>
              <div className="focus-stat">
                <span className="focus-stat__label">Stage runtime</span>
                <strong className="focus-stat__value">{formatElapsedTime(stageRuntime)}</strong>
              </div>
              <div className="focus-stat">
                <span className="focus-stat__label">Completed</span>
                <strong className="focus-stat__value">{totalCompletedTasks}</strong>
              </div>
              <div className="focus-stat">
                <span className="focus-stat__label">Model / cycle</span>
                <strong className="focus-stat__value">
                  {snapshot.metrics.currentModel || '--'} · {snapshot.metrics.cycleNumber ?? '--'}
                </strong>
              </div>
            </div>

            <div className="focus-stagebar" aria-hidden="true">
              {PIPELINE_STAGES.map((stage, index) => {
                const activeIndex = activeStage ? PIPELINE_STAGES.indexOf(activeStage) : -1;
                const state =
                  activeIndex === -1
                    ? 'pending'
                    : index < activeIndex
                      ? 'done'
                      : index === activeIndex
                        ? 'active'
                        : 'pending';

                return (
                  <div key={stage} className={`focus-stagebar__item focus-stagebar__item--${state}`}>
                    <span className="focus-stagebar__dot" />
                    <span className="focus-stagebar__label">{formatStageLabel(stage)}</span>
                  </div>
                );
              })}
            </div>

            <div className="focus-columns">
              <article className="info-panel">
                <div className="info-panel__heading">Recent pulses</div>
                <div className="pulse-list">
                  {recentLogLines.length ? (
                    recentLogLines.map((line: string) => (
                      <div key={line} className="pulse-list__item">
                        {line}
                      </div>
                    ))
                  ) : (
                    <div className="info-panel__empty">Waiting for dashboard log lines.</div>
                  )}
                </div>
              </article>

              <article className="info-panel">
                <div className="info-panel__heading">Validation surface</div>
                <div className="suite-stack">
                  {suiteEntries.length ? (
                    suiteEntries.map(([suiteName, suite]: [string, DashboardTestSuite]) => {
                      const passRatio = suite.total > 0 ? suite.passed / Math.max(1, suite.total) : 0;
                      return (
                        <div key={suiteName} className={`suite-card ${suite.active ? 'suite-card--active' : ''}`}>
                          <div className="suite-card__topline">
                            <span>{prettifySuiteName(suiteName)}</span>
                            <span>{suite.passed}/{suite.total || '--'}</span>
                          </div>
                          <div className="suite-card__bar">
                            <div className="suite-card__fill" style={{ width: `${passRatio * 100}%` }} />
                          </div>
                          <div className="suite-card__meta">
                            <span>{suite.failed} fail</span>
                            <span>{suite.active ? 'running' : 'queued'}</span>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="info-panel__empty">No live suites have surfaced yet.</div>
                  )}
                </div>
              </article>
            </div>
          </section>

          <aside className="deck-panel deck-panel--intel">
            <article className="info-panel">
              <div className="info-panel__heading">Queue Horizon</div>
              <div className="queue-list">
                {upcomingTasks.length ? (
                  upcomingTasks.map((task: DashboardTask) => (
                    <div key={String(task.id)} className="queue-list__item">
                      <span className="queue-list__id">{task.id}</span>
                      <span className="queue-list__name">{truncateMiddle(task.name, 70)}</span>
                    </div>
                  ))
                ) : (
                  <div className="info-panel__empty">No queued tasks visible.</div>
                )}
              </div>
            </article>

            <article className="info-panel">
              <div className="info-panel__heading">Recent Completions</div>
              <div className="queue-list">
                {completedTasks.length ? (
                  completedTasks.map((task: DashboardTask) => (
                    <div key={String(task.id)} className="queue-list__item queue-list__item--complete">
                      <span className="queue-list__id">{task.id}</span>
                      <span className="queue-list__name">{truncateMiddle(task.name, 66)}</span>
                    </div>
                  ))
                ) : (
                  <div className="info-panel__empty">Completion history will appear here.</div>
                )}
              </div>
            </article>

            <article className="info-panel">
              <div className="info-panel__heading">Live Signal</div>
              <div className="signal-stack">
                <div className="signal-stack__row">
                  <span>Loop posture</span>
                  <strong>{formatLoopLabel(snapshot)}</strong>
                </div>
                <div className="signal-stack__row">
                  <span>Breakdown</span>
                  <strong>
                    {progressBreakdown.done} done · {progressBreakdown.active} active · {progressBreakdown.pending} pending
                  </strong>
                </div>
                <div className="signal-stack__row">
                  <span>Latest commit</span>
                  <strong title={snapshot.latestCommit.message}>
                    {snapshot.latestCommit.hash ? snapshot.latestCommit.hash.slice(0, 7) : '--'}
                  </strong>
                </div>
                <div className="signal-stack__message" title={snapshot.latestCommit.message}>
                  {snapshot.latestCommit.message || 'Commit metadata will land here once Track3 sees git activity.'}
                </div>
              </div>
            </article>
          </aside>
        </div>
      </div>
    </section>
  );
}
