export function formatElapsedTime(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) {
    return '--';
  }

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

export function formatMillions(value: number): string {
  if (!Number.isFinite(value) || value <= 0) {
    return '0.0M';
  }
  return `${(value / 1_000_000).toFixed(1)}M`;
}

export function truncateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }

  if (maxLength <= 1) {
    return value.slice(0, maxLength);
  }

  return `${value.slice(0, maxLength - 1)}…`;
}

export function countProgress(tasksDone: number, totalTasks: number): number {
  if (totalTasks <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, tasksDone / totalTasks));
}

export function formatTimestampAge(ageSeconds: number | null): string {
  if (ageSeconds === null || ageSeconds < 0) {
    return '--';
  }
  return `${Math.floor(ageSeconds)}s ago`;
}

export function prettifySuiteName(key: string): string {
  return key.replace(/_/g, ' ');
}

export function prettifyIdentifier(value: string | null | undefined, fallback = '--'): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    return fallback;
  }

  return trimmed
    .split(/[.\s_-]+/g)
    .filter(Boolean)
    .map((part) => {
      if (/^[A-Z0-9]+$/.test(part)) {
        return part;
      }
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(' ');
}
