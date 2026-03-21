import { React } from '../react-global.js';
import { PIPELINE_STAGES } from '../constants.js';
import type { DashboardSnapshot } from '../types.js';
import { getActiveTask, getActiveStage } from '../utils/telemetry.js';

interface TaskBarProps {
  snapshot: DashboardSnapshot;
}

export function TaskBar({ snapshot }: TaskBarProps) {
  const activeTask = getActiveTask(snapshot);
  const activeStage = getActiveStage(snapshot);
  const activeStageIndex = activeStage ? PIPELINE_STAGES.indexOf(activeStage) : -1;

  return (
    <div className="task-bar" aria-label="Current task status">
      <div className="task-bar__counter">
        {snapshot.pipeline.currentTaskIndex} / {snapshot.pipeline.totalTasks}
      </div>
      <div className="task-bar__name" title={activeTask?.name || ''}>
        {activeTask?.name || ''}
      </div>
      <div className="task-bar__pipeline" aria-hidden="true">
        {PIPELINE_STAGES.map((stage, index) => {
          const state =
            activeStageIndex === -1
              ? 'pending'
              : index < activeStageIndex
                ? 'done'
                : index === activeStageIndex
                  ? 'active'
                  : 'pending';

          return <span key={stage} className={`task-bar__stage task-bar__stage--${state}`} />;
        })}
      </div>
    </div>
  );
}
