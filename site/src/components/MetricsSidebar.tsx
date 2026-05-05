import { React, useEffect, useRef, useState } from '../react-global.js';
import type { ActiveLoop, DashboardQueueCounts, DashboardSnapshot } from '../types.js';
import {
  countProgress,
  formatElapsedTime,
  formatMillions,
  formatTimestampAge,
  prettifyIdentifier,
  truncateMiddle,
} from '../utils/format.js';
import { getCompletedTaskCount, getProgressBreakdown } from '../utils/telemetry.js';
import { getDisplayName } from '../workers.js';

interface MetricsSidebarProps {
  snapshot: DashboardSnapshot;
  showStaleIndicator: boolean;
  staleAgeSeconds: number | null;
  lastEventAgeSeconds: number | null;
}

const PLANES: ActiveLoop[] = ['execution', 'planning', 'learning'];

function MetricGroup({ label, children }: { label: string; children: any }) {
  return (
    <section className="metric-group">
      <div className="metric-group__label">{label}</div>
      <div className="metric-group__body">{children}</div>
    </section>
  );
}

function formatRuntimeState(snapshot: DashboardSnapshot): string {
  if (snapshot.runtime.paused) {
    return 'Paused';
  }
  if (snapshot.runtime.stopRequested) {
    return 'Stopping';
  }
  if (snapshot.runtime.processRunning) {
    return 'Running';
  }
  return 'Standby';
}

function countQueue(counts: DashboardQueueCounts): number {
  return counts.queue + counts.active + counts.blocked;
}

function formatQueueLine(snapshot: DashboardSnapshot): string {
  return PLANES.map((plane) => `${plane} ${countQueue(snapshot.queues[plane])}`).join(' / ');
}

function MetricLine({ label, value }: { label: string; value: any }) {
  return (
    <div className="metric-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function MetricsSidebar({ snapshot, showStaleIndicator, staleAgeSeconds, lastEventAgeSeconds }: MetricsSidebarProps) {
  const completedTasks = getCompletedTaskCount(snapshot);
  const progressRatio = countProgress(completedTasks, snapshot.pipeline.totalTasks || snapshot.tasks.length);
  const progressBreakdown = getProgressBreakdown(snapshot);
  const activeAgentName = snapshot.runtime.activeStage
    ? getDisplayName(snapshot.runtime.activeStage)
    : prettifyIdentifier(snapshot.runtime.activeStageLabel ?? snapshot.pipeline.rawAgent);
  const runtimeState = formatRuntimeState(snapshot);
  const workItem = snapshot.runtime.activeWorkItemId || snapshot.runtime.activeRunId || 'work item pending';
  const planId = snapshot.runtime.compiledPlanId ? truncateMiddle(snapshot.runtime.compiledPlanId, 32) : 'plan pending';
  const planState = snapshot.runtime.compiledPlanCurrentness || '--';
  const loopLabel = snapshot.runtime.activeLoopId || snapshot.loop.activeLoop;
  const latestHash = snapshot.latestCommit.hash ? snapshot.latestCommit.hash.slice(0, 7) : '--';
  const latestMessage = snapshot.latestCommit.message || '--';
  const feedLabel = snapshot.tracker.syncMode === 'event_driven' ? 'Event feed' : 'Polling live';
  const feedSubline = showStaleIndicator
    ? `Last fetch ${formatTimestampAge(staleAgeSeconds)}`
    : snapshot.tracker.syncMode === 'event_driven'
      ? `Last event ${formatTimestampAge(lastEventAgeSeconds)}`
      : 'state feed connected';
  const modelRuntimeSeconds = snapshot.metrics.modelRuntimeSeconds || snapshot.elapsedSeconds;
  const totalModelRuntimeSeconds =
    snapshot.metrics.totalModelRuntimeSeconds || snapshot.runtime.totalModelRuntimeSeconds;
  const primaryRuntimeSeconds = totalModelRuntimeSeconds || modelRuntimeSeconds;
  const primaryRuntimeLabel = totalModelRuntimeSeconds > 0 ? 'total model runtime' : 'session model runtime';
  const wallClockSeconds = snapshot.runtime.wallClockElapsedSeconds;
  const showDaemonModel = totalModelRuntimeSeconds > modelRuntimeSeconds + 60 && modelRuntimeSeconds > 0;
  const showDaemonUptime = wallClockSeconds > modelRuntimeSeconds + 60;

  const [commitFlash, setCommitFlash] = useState(false);
  const previousCommitHashRef = useRef(snapshot.latestCommit.hash);

  useEffect(() => {
    const previousHash = previousCommitHashRef.current;
    const nextHash = snapshot.latestCommit.hash;
    previousCommitHashRef.current = nextHash;

    if (previousHash && nextHash && previousHash !== nextHash) {
      setCommitFlash(true);
      const timer = window.setTimeout(() => setCommitFlash(false), 320);
      return () => window.clearTimeout(timer);
    }

    return undefined;
  }, [snapshot.latestCommit.hash]);

  return (
    <aside className="metrics-sidebar" aria-label="Run metrics">
      <MetricGroup label="Runtime Identity">
        <div className={`metric-value metric-value--${runtimeState.toLowerCase()}`}>{runtimeState}</div>
        <div className="metric-subline">
          {snapshot.runtime.baselineSeedPackageVersion
            ? `Millrace ${snapshot.runtime.baselineSeedPackageVersion}`
            : snapshot.runtime.runtimeMode || 'runtime pending'}
        </div>
        <MetricLine label="run" value={snapshot.runId || 'run pending'} />
        <MetricLine label="mode" value={snapshot.runtime.activeModeId || 'mode pending'} />
        <MetricLine label="loop" value={loopLabel} />
        <MetricLine label="plan" value={`${planState} / ${planId}`} />
      </MetricGroup>

      <MetricGroup label="Work State">
        <div className={`metric-active-agent ${snapshot.runtime.activeStageLabel || snapshot.runtime.activeStage || snapshot.pipeline.currentAgent ? '' : 'metric-value--muted'}`}>
          {activeAgentName}
        </div>
        <div className="metric-subline">{workItem}</div>
        <MetricLine label="queue" value={formatQueueLine(snapshot)} />
        <MetricLine
          label="tasks"
          value={`${progressBreakdown.done} done / ${progressBreakdown.active} active / ${progressBreakdown.pending} pending`}
        />
        <div className="progress-bar" aria-hidden="true">
          <div className="progress-bar__fill" style={{ width: `${progressRatio * 100}%` }} />
        </div>
        <div className="metric-subline">
          {completedTasks} / {snapshot.pipeline.totalTasks || snapshot.tasks.length || 0} execution work items
        </div>
      </MetricGroup>

      <MetricGroup label="Usage">
        <div className={`metric-value ${primaryRuntimeSeconds > 0 ? '' : 'metric-value--muted'}`}>
          {formatElapsedTime(primaryRuntimeSeconds)}
        </div>
        <div className="metric-subline">{primaryRuntimeLabel}</div>
        {showDaemonModel ? (
          <div className="metric-subline">current daemon model {formatElapsedTime(modelRuntimeSeconds)}</div>
        ) : null}
        {showDaemonUptime ? <div className="metric-subline">daemon uptime {formatElapsedTime(wallClockSeconds)}</div> : null}
        <div className="metric-subline metric-subline--tokens">IN {formatMillions(snapshot.metrics.tokensIn)}</div>
        <div className="metric-subline metric-subline--tokens">
          CACHED {formatMillions(snapshot.metrics.cachedTokens)}&nbsp;&nbsp;OUT {formatMillions(snapshot.metrics.tokensOut)}
        </div>
        <div className="metric-subline">{snapshot.metrics.currentModel || 'model pending'}</div>
      </MetricGroup>

      <MetricGroup label="Output">
        <MetricLine label="open targets" value={snapshot.runtime.closure.openCount} />
        <div className="metric-subline">
          {snapshot.runtime.closure.rootSpecId || (snapshot.runtime.closure.blockedByLineageWork ? 'lineage blocked' : 'no open target')}
        </div>
        <div className={`latest-commit ${commitFlash ? 'latest-commit--flash' : ''}`}>
          <div className="latest-commit__hash">{latestHash}</div>
          <div className="latest-commit__message" title={latestMessage}>
            {latestMessage}
          </div>
        </div>
      </MetricGroup>

      <MetricGroup label="Feed">
        <div className={`metric-value ${showStaleIndicator ? 'metric-value--warning' : 'metric-value--positive'}`}>
          {showStaleIndicator ? 'Feed stale' : feedLabel}
        </div>
        <div className="metric-subline">{feedSubline}</div>
        <div className="metric-subline">public state / live-state.json</div>
      </MetricGroup>
    </aside>
  );
}
