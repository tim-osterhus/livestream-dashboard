import { React, useEffect, useRef, useState } from '../react-global.js';
import { COLORS } from '../constants.js';
import type { DashboardSnapshot } from '../types.js';
import { interpolateHex } from '../utils/colors.js';
import {
  countProgress,
  formatElapsedTime,
  formatMillions,
  formatTimestampAge,
} from '../utils/format.js';
import { getCompletedTaskCount, getProgressBreakdown } from '../utils/telemetry.js';
import { getDisplayName } from '../workers.js';

interface MetricsSidebarProps {
  snapshot: DashboardSnapshot;
  showStaleIndicator: boolean;
  staleAgeSeconds: number | null;
}

function MetricGroup({ label, children }: { label: string; children: any }) {
  return (
    <section className="metric-group">
      <div className="metric-group__label">{label}</div>
      <div className="metric-group__body">{children}</div>
    </section>
  );
}

function formatLoopLabel(snapshot: DashboardSnapshot): string {
  if (snapshot.loop.activeLoop === 'research') {
    return `Research / ${snapshot.loop.researchMode || 'goalspec'}`;
  }
  return 'Orchestration / Forge';
}

export function MetricsSidebar({ snapshot, showStaleIndicator, staleAgeSeconds }: MetricsSidebarProps) {
  const completedTasks = getCompletedTaskCount(snapshot);
  const progressRatio = countProgress(completedTasks, snapshot.pipeline.totalTasks);
  const progressBreakdown = getProgressBreakdown(snapshot);
  const activeAgentName = getDisplayName(snapshot.pipeline.currentAgent);
  const costColor = interpolateHex(COLORS.muted, COLORS.heatHot, progressRatio);

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
      <MetricGroup label="Run">
        <div className="metric-value">{formatLoopLabel(snapshot)}</div>
        <div className="metric-subline">{snapshot.runId || 'run-id pending'}</div>
      </MetricGroup>

      <MetricGroup label="Cost">
        <div className="metric-cost" style={{ color: costColor }}>
          $200
        </div>
      </MetricGroup>

      <MetricGroup label="Elapsed Time">
        <div className={`metric-value ${snapshot.elapsedSeconds > 0 ? '' : 'metric-value--muted'}`}>
          {formatElapsedTime(snapshot.elapsedSeconds)}
        </div>
      </MetricGroup>

      <MetricGroup label="Active Agent">
        <div className={`metric-active-agent ${snapshot.pipeline.currentAgent ? '' : 'metric-value--muted'}`}>
          {activeAgentName}
        </div>
      </MetricGroup>

      <MetricGroup label="Progress">
        <div className="progress-bar" aria-hidden="true">
          <div className="progress-bar__fill" style={{ width: `${progressRatio * 100}%` }} />
        </div>
        <div className="metric-subline">
          {progressBreakdown.done} done · {progressBreakdown.active} active · {progressBreakdown.pending} pending
        </div>
      </MetricGroup>

      <MetricGroup label="Tokens">
        <div className="metric-subline metric-subline--tokens">
          IN {formatMillions(snapshot.metrics.tokensIn)}
        </div>
        <div className="metric-subline metric-subline--tokens">
          CACHED {formatMillions(snapshot.metrics.cachedTokens)}&nbsp;&nbsp;OUT {formatMillions(snapshot.metrics.tokensOut)}
        </div>
      </MetricGroup>

      <MetricGroup label="Latest Commit">
        <div className={`latest-commit ${commitFlash ? 'latest-commit--flash' : ''}`}>
          <div className="latest-commit__hash">{snapshot.latestCommit.hash ? snapshot.latestCommit.hash.slice(0, 7) : '--'}</div>
          <div className="latest-commit__message" title={snapshot.latestCommit.message}>
            {snapshot.latestCommit.message || '--'}
          </div>
        </div>
      </MetricGroup>

      <MetricGroup label="Feed Health">
        <div className={`metric-value ${showStaleIndicator ? 'metric-value--warning' : 'metric-value--positive'}`}>
          {showStaleIndicator ? 'Tracker stale' : 'Polling live'}
        </div>
        <div className="metric-subline">
          {showStaleIndicator ? `Last updated ${formatTimestampAge(staleAgeSeconds)}` : 'Auto-refresh enabled'}
        </div>
      </MetricGroup>

      <div className="sidebar-footer">
        Preliminary livestream surface
      </div>
    </aside>
  );
}
