import { React, useMemo } from '../react-global.js';
import type {
  ActiveLoop,
  DashboardQueueCounts,
  DashboardSnapshot,
  DashboardTask,
  PipelineStage,
} from '../types.js';
import { formatElapsedTime, truncateMiddle } from '../utils/format.js';
import { getActiveStage, getActiveTask } from '../utils/telemetry.js';
import { getDisplayName, getStageSequence } from '../workers.js';

interface WorkshopSceneProps {
  snapshot: DashboardSnapshot;
}

const PLANES: ActiveLoop[] = ['execution', 'planning', 'learning'];

function formatStageLabel(stage: PipelineStage | null): string {
  if (!stage) {
    return 'Standby';
  }
  return getDisplayName(stage, stage.replace(/_/g, ' '));
}

function formatPlaneLabel(plane: ActiveLoop): string {
  return plane.charAt(0).toUpperCase() + plane.slice(1);
}

function countQueue(counts: DashboardQueueCounts): number {
  return counts.queue + counts.active + counts.blocked;
}

function titleizeWorkItemId(value: string): string {
  return value
    .split(/[-_]+/g)
    .filter(Boolean)
    .map((part) => (part.length <= 3 && /\d/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ');
}

function getFocusTitle(snapshot: DashboardSnapshot, activeTask: DashboardTask | null): string {
  if (activeTask?.name && activeTask.name !== '—') {
    return activeTask.name;
  }
  if (snapshot.runtime.activeWorkItemId) {
    return titleizeWorkItemId(snapshot.runtime.activeWorkItemId);
  }
  if (snapshot.runtime.processRunning) {
    return 'Runtime active';
  }
  return 'Runtime standby';
}

function getRuntimeLine(snapshot: DashboardSnapshot): string {
  const parts = [
    snapshot.runtime.activeModeId || 'mode pending',
    snapshot.runtime.compiledPlanCurrentness || snapshot.runtime.compiledPlanId || 'plan pending',
    snapshot.runtime.activeRunId || snapshot.runtime.watcherMode || 'run pending',
  ];
  return parts.filter(Boolean).join(' / ');
}

function getStageRuntimeSeconds(snapshot: DashboardSnapshot): number {
  if (!snapshot.pipeline.agentStartedAt) {
    return 0;
  }

  const startedAtMs = Date.parse(snapshot.pipeline.agentStartedAt);
  const running = snapshot.runtime.processRunning && !snapshot.runtime.paused && !snapshot.runtime.stopRequested;
  const timestampMs = running ? Date.now() : snapshot.timestamp ? Date.parse(snapshot.timestamp) : NaN;
  if (!Number.isFinite(startedAtMs) || !Number.isFinite(timestampMs)) {
    return 0;
  }

  return Math.max(0, Math.floor((timestampMs - startedAtMs) / 1000));
}

function formatStatusMarker(marker: string | null | undefined): string {
  if (!marker) {
    return 'state idle';
  }

  const cleaned = marker.replace(/^#+\s*/, '').trim();
  return cleaned ? `state ${cleaned.toLowerCase()}` : 'state idle';
}

export function WorkshopScene({ snapshot }: WorkshopSceneProps) {
  const activeTask = getActiveTask(snapshot);
  const activeStage = getActiveStage(snapshot);
  const stageSequence = getStageSequence(snapshot.loop.activeLoop);
  const activeIndex = activeStage ? stageSequence.indexOf(activeStage) : -1;
  const stageRuntime = getStageRuntimeSeconds(snapshot);
  const focusTitle = getFocusTitle(snapshot, activeTask);
  const runtimeLine = getRuntimeLine(snapshot);
  const completedTasks = useMemo(
    () => snapshot.tasks.filter((task) => task.status === 'complete').slice(-5).reverse(),
    [snapshot.tasks],
  );
  const upcomingTasks = useMemo(
    () => snapshot.tasks.filter((task) => task.status === 'pending').slice(0, 6),
    [snapshot.tasks],
  );
  const queuedTotal = PLANES.reduce((total, plane) => total + countQueue(snapshot.queues[plane]), 0);
  const statusText = snapshot.runtime.paused
    ? 'Paused'
    : snapshot.runtime.stopRequested
      ? 'Stopping'
      : snapshot.runtime.processRunning
        ? 'Running'
        : 'Standby';

  return (
    <section className="workshop-shell" aria-label="Millrace operations">
      <div className="scene-gridlines" aria-hidden="true" />

      <div className="command-deck">
        <header className="command-deck__header">
          <div className="command-deck__brand" aria-label="Millrace live runtime surface">
            <img className="brand-mark" src="./MillraceIconSignalNav.png" alt="" aria-hidden="true" />
            <span className="brand-name">Millrace</span>
            <span className="brand-tag">Live Surface</span>
          </div>
          <div className={`runtime-pill runtime-pill--${statusText.toLowerCase()}`}>
            <span className="runtime-pill__dot" />
            {statusText}
          </div>
        </header>

        <div className="command-deck__meta-strip" aria-label="Dashboard surface metadata">
          <span>surface <strong>runtime state</strong></span>
          <span>source <strong>live-state.json</strong></span>
          <span>loop <strong>{snapshot.loop.activeLoop}</strong></span>
          <span>control <strong>{snapshot.runtime.activeModeId || 'mode pending'}</strong></span>
        </div>

        <div className="command-deck__body">
          <section className="deck-panel deck-panel--focus">
            <div className="focus-summary">
              <div className="focus-hero">
                <div className="focus-hero__eyebrow">
                  Runtime surface / {formatPlaneLabel(snapshot.loop.activeLoop)} / {formatStageLabel(activeStage)}
                </div>
                <h2 className="focus-hero__task" title={focusTitle}>
                  {truncateMiddle(focusTitle, 120)}
                </h2>
                <div className="focus-hero__subline">{runtimeLine}</div>
              </div>
            </div>

            <div className="focus-stats">
              <div className="focus-stat">
                <span className="focus-stat__label">Backlog</span>
                <strong className="focus-stat__value">{queuedTotal}</strong>
              </div>
              <div className="focus-stat">
                <span className="focus-stat__label">Stage Runtime</span>
                <strong className="focus-stat__value">{formatElapsedTime(stageRuntime)}</strong>
              </div>
              <div className="focus-stat">
                <span className="focus-stat__label">Cycle</span>
                <strong className="focus-stat__value">{snapshot.metrics.cycleNumber ?? '--'}</strong>
              </div>
            </div>

            <div className="focus-stagebar" aria-hidden="true">
              {stageSequence.map((stage, index) => {
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

            <div className="plane-grid">
              {PLANES.map((plane) => {
                const counts = snapshot.queues[plane];
                const isActive = snapshot.loop.activeLoop === plane;
                return (
                  <article key={plane} className={`plane-panel ${isActive ? 'plane-panel--active' : ''}`}>
                    <div className="plane-panel__header">
                      <span>{formatPlaneLabel(plane)}</span>
                      <strong>{countQueue(counts)}</strong>
                    </div>
                    <div className="plane-panel__lanes">
                      <span>queue {counts.queue}</span>
                      <span>active {counts.active}</span>
                      <span>blocked {counts.blocked}</span>
                      <span>done {counts.done}</span>
                    </div>
                    <div className="plane-panel__marker">
                      {formatStatusMarker(snapshot.runtime.statusMarkers[plane])}
                    </div>
                  </article>
                );
              })}
            </div>

            <div className="ops-grid">
              <article className="info-panel info-panel--queue">
                <div className="info-panel__heading">Queued Work</div>
                <div className="queue-list">
                  {upcomingTasks.length ? (
                    upcomingTasks.map((task: DashboardTask) => (
                      <div key={String(task.id)} className="queue-list__item">
                        <span className="queue-list__id">{task.id}</span>
                        <span className="queue-list__name">{truncateMiddle(task.name, 140)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="info-panel__empty">No queued execution work.</div>
                  )}
                </div>
              </article>

              <article className="info-panel">
                <div className="info-panel__heading">Completed Work</div>
                <div className="queue-list">
                  {completedTasks.length ? (
                    completedTasks.map((task: DashboardTask) => (
                      <div key={String(task.id)} className="queue-list__item queue-list__item--complete">
                        <span className="queue-list__id">{task.id}</span>
                        <span className="queue-list__name">{truncateMiddle(task.name, 140)}</span>
                      </div>
                    ))
                  ) : (
                    <div className="info-panel__empty">No completed execution work.</div>
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
