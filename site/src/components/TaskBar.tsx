import { React } from '../react-global.js';
import type { DashboardSnapshot } from '../types.js';
import { getActiveTask, getActiveStage } from '../utils/telemetry.js';
import { getDisplayName, getStageSequence } from '../workers.js';

interface TaskBarProps {
  snapshot: DashboardSnapshot;
}

export function TaskBar({ snapshot }: TaskBarProps) {
  const activeTask = getActiveTask(snapshot);
  const activeStage = getActiveStage(snapshot);
  const stageSequence = getStageSequence(snapshot.loop.activeLoop);
  const activeStageIndex = activeStage ? stageSequence.indexOf(activeStage) : -1;
  const stageLabel = getDisplayName(activeStage, 'Idle');
  const isStandby = !snapshot.pipeline.currentAgent && snapshot.pipeline.totalTasks === 0;
  const taskLabel = isStandby ? 'Waiting for first loop signal' : (activeTask?.name || 'Waiting for first loop signal');

  return (
    <div className="task-bar" aria-label="Current task status">
      <div className="task-bar__counter">
        {snapshot.pipeline.currentTaskIndex} / {snapshot.pipeline.totalTasks}
      </div>
      <div className="task-bar__name" title={taskLabel}>
        {taskLabel}
      </div>
      <div className="task-bar__meta">
        {stageLabel}
      </div>
      <div className="task-bar__pipeline" aria-hidden="true">
        {stageSequence.map((stage, index) => {
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
