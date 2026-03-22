import { React } from './react-global.js';
import { MetricsSidebar } from './components/MetricsSidebar.js';
import { LogTicker } from './components/LogTicker.js';
import { WorkshopScene } from './components/WorkshopScene.js';
import { useDashboardData } from './hooks/useDashboardData.js';

export function App() {
  const {
    snapshot,
    logLines,
    showStaleIndicator,
    staleAgeSeconds,
  } = useDashboardData();

  return (
    <main className="dashboard-root">
      <div className="dashboard-layout">
        <div className="dashboard-main">
          <WorkshopScene snapshot={snapshot} />
          <LogTicker lines={logLines} />
        </div>
        <MetricsSidebar
          snapshot={snapshot}
          showStaleIndicator={showStaleIndicator}
          staleAgeSeconds={staleAgeSeconds}
        />
      </div>
    </main>
  );
}
