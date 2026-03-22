import { React, useEffect, useMemo, useRef, useState } from '../react-global.js';
import { PIPELINE_STAGES } from '../constants.js';
import type {
  DashboardSnapshot,
  DashboardTask,
  PipelineStage,
} from '../types.js';
import { formatElapsedTime, truncateMiddle } from '../utils/format.js';
import { getActiveStage, getActiveTask } from '../utils/telemetry.js';

interface WorkshopSceneProps {
  snapshot: DashboardSnapshot;
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

function getFocusTitle(snapshot: DashboardSnapshot, activeTask: DashboardTask | null): string {
  if (!snapshot.pipeline.currentAgent && snapshot.pipeline.totalTasks === 0) {
    return 'Awaiting first loop event';
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
    return 'Start either logged loop and this surface will switch from standby into live queue, commit, and transcript telemetry automatically.';
  }
  if (snapshot.loop.activeLoop === 'research') {
    return 'Use this surface to make decomposition, audit posture, and incident handling legible at a glance.';
  }
  return 'Execution is live. Keep the operator focused on queue movement, commit activity, and the live transcript rather than decorative scaffolding.';
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

export function WorkshopScene({ snapshot }: WorkshopSceneProps) {
  const [researchSwapPulse, setResearchSwapPulse] = useState(false);
  const previousResearchModeRef = useRef(snapshot.loop.researchMode as DashboardSnapshot['loop']['researchMode']);

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

  const activeTask = getActiveTask(snapshot);
  const activeStage = getActiveStage(snapshot);
  const completedTasks = useMemo(
    () => snapshot.tasks.filter((task) => task.status === 'complete').slice(-4).reverse(),
    [snapshot.tasks],
  );
  const upcomingTasks = useMemo(
    () => snapshot.tasks.filter((task) => task.status === 'pending').slice(0, 5),
    [snapshot.tasks],
  );
  const stageRuntime = getStageRuntimeSeconds(snapshot);
  const focusTitle = getFocusTitle(snapshot, activeTask);
  const focusTagline = getFocusTagline(snapshot);
  return (
    <section className="workshop-shell" aria-label="Mission control command deck">
      <BackdropLayer type="orchestration" visible={snapshot.loop.activeLoop === 'orchestration'} pulsing={false} />
      <BackdropLayer type="research" visible={snapshot.loop.activeLoop === 'research'} pulsing={researchSwapPulse} />

      <div className={`command-deck ${researchSwapPulse ? 'command-deck--swap' : ''}`}>
        <header className="command-deck__header">
          <div>
            <div className="command-deck__title">Livestream dashboard</div>
          </div>
        </header>

        <div className="command-deck__body">
          <section className="deck-panel deck-panel--focus">
            <div className="focus-summary">
              <div className="focus-hero">
                <div className="focus-hero__eyebrow">Millrace Mission Control</div>
                <h2 className="focus-hero__task" title={focusTitle}>
                  {focusTitle}
                </h2>
                <div className="focus-hero__subline">{focusTagline}</div>
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

            <div className="ops-grid">
              <article className="info-panel info-panel--queue">
                <div className="info-panel__heading">Queue horizon</div>
                <div className="queue-list">
                  {upcomingTasks.length ? (
                    upcomingTasks.map((task: DashboardTask) => (
                      <div key={String(task.id)} className="queue-list__item">
                        <span className="queue-list__id">{task.id}</span>
                        <span className="queue-list__name">{truncateMiddle(task.name, 140)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="info-panel__empty">No queued tasks visible yet.</div>
                  )}
                </div>
              </article>

              <article className="info-panel">
                <div className="info-panel__heading">Recent completions</div>
                <div className="queue-list">
                  {completedTasks.length ? (
                    completedTasks.map((task: DashboardTask) => (
                      <div key={String(task.id)} className="queue-list__item queue-list__item--complete">
                        <span className="queue-list__id">{task.id}</span>
                        <span className="queue-list__name">{truncateMiddle(task.name, 140)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="info-panel__empty">Completion history will appear here.</div>
                  )}
                </div>
              </article>
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}
