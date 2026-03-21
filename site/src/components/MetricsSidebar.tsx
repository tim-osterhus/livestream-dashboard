import { React, useEffect, useRef, useState } from '../react-global.js';
import { COLORS } from '../constants.js';
import type { DashboardSnapshot } from '../types.js';
import { interpolateHex } from '../utils/colors.js';
import {
  countProgress,
  formatElapsedTime,
  formatMillions,
  formatTimestampAge,
  prettifySuiteName,
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

export function MetricsSidebar({ snapshot, showStaleIndicator, staleAgeSeconds }: MetricsSidebarProps) {
  const completedTasks = getCompletedTaskCount(snapshot);
  const progressRatio = countProgress(completedTasks, snapshot.pipeline.totalTasks);
  const progressBreakdown = getProgressBreakdown(snapshot);
  const activeAgentName = getDisplayName(snapshot.pipeline.currentAgent);
  const costColor = interpolateHex(COLORS.muted, COLORS.heatHot, progressRatio);

  const [commitFlash, setCommitFlash] = useState(false);
  const [activatedSuites, setActivatedSuites] = useState([] as string[]);
  const previousCommitHashRef = useRef(snapshot.latestCommit.hash);
  const previousTestsRef = useRef(snapshot.tests);

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

  useEffect(() => {
    const previousTests = previousTestsRef.current;
    const nextActivated = Object.entries(snapshot.tests)
      .filter(([suiteName, suite]) => {
        const previousSuite = previousTests[suiteName];
        const previousVisible = Boolean(previousSuite?.active || previousSuite?.total || previousSuite?.passed || previousSuite?.failed);
        const nextVisible = Boolean(suite.active || suite.total || suite.passed || suite.failed);
        return nextVisible && !previousVisible;
      })
      .map(([suiteName]) => suiteName);

    previousTestsRef.current = snapshot.tests;

    if (!nextActivated.length) {
      return undefined;
    }

    setActivatedSuites(nextActivated);
    const timer = window.setTimeout(() => setActivatedSuites([]), 650);
    return () => window.clearTimeout(timer);
  }, [snapshot.tests]);

  const hasAnyLiveSuites = Object.values(snapshot.tests).some(
    (suite) => suite.active || suite.total > 0 || suite.passed > 0 || suite.failed > 0,
  );

  const suiteEntries = Object.entries(snapshot.tests).filter(([, suite]) => {
    if (!hasAnyLiveSuites) {
      return true;
    }
    return suite.active || suite.total > 0 || suite.passed > 0 || suite.failed > 0;
  });

  return (
    <aside className="metrics-sidebar" aria-label="Run metrics">
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
        <div className="metric-subline">
          {snapshot.metrics.currentModel || '--'}
          {' · cycle '}
          {snapshot.metrics.cycleNumber ?? '--'}
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
          IN {formatMillions(snapshot.metrics.tokensIn)}&nbsp;&nbsp;OUT {formatMillions(snapshot.metrics.tokensOut)}
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

      <MetricGroup label="Test Results">
        <div className="test-results">
          {suiteEntries.map(([suiteName, suite]) => {
            const isAwaiting = !suite.active && suite.total === 0 && suite.passed === 0 && suite.failed === 0;
            const isActivated = activatedSuites.includes(suiteName);

            return (
              <div
                key={suiteName}
                className={`test-suite-row ${isAwaiting ? 'test-suite-row--awaiting' : ''} ${isActivated ? 'test-suite-row--revealed' : ''}`}
              >
                <div className="test-suite-row__name">{prettifySuiteName(suiteName)}</div>
                {isAwaiting ? (
                  <div className="test-suite-row__awaiting">Awaiting activation</div>
                ) : (
                  <div className="test-suite-row__stats">
                    <span className="test-suite-row__pass">{suite.passed} pass</span>
                    <span className="test-suite-row__fail">{suite.failed} fail</span>
                    <span className="test-suite-row__total">/ {suite.total}</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </MetricGroup>

      <div className="sidebar-footer">
        {showStaleIndicator ? `Last updated ${formatTimestampAge(staleAgeSeconds)}` : ''}
      </div>
    </aside>
  );
}
