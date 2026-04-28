import { React, useEffect, useRef, useState } from '../react-global.js';
import { loadRuntimeConfig } from '../config.js';
import type { CanonicalAgent, DashboardSnapshot, RawDashboardPayload, ResolvedConfig } from '../types.js';
import { createIdleSnapshot, mergeLogLines, normalizeSnapshot } from '../utils/telemetry.js';

function parseTimestampToMs(timestamp: string | null): number | null {
  if (!timestamp) {
    return null;
  }
  const parsed = Date.parse(timestamp);
  return Number.isFinite(parsed) ? parsed : null;
}

export interface DashboardDataState {
  config: ResolvedConfig | null;
  snapshot: DashboardSnapshot;
  logLines: string[];
  previousAgent: CanonicalAgent | null;
  isInitialLoading: boolean;
  showStaleIndicator: boolean;
  staleAgeSeconds: number | null;
  lastEventAgeSeconds: number | null;
}

export function useDashboardData(): DashboardDataState {
  const [config, setConfig] = useState(null as ResolvedConfig | null);
  const [snapshot, setSnapshot] = useState(createIdleSnapshot() as DashboardSnapshot);
  const [logLines, setLogLines] = useState(createIdleSnapshot().logLines as string[]);
  const [previousAgent, setPreviousAgent] = useState(null as CanonicalAgent | null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [consecutiveFetchFailures, setConsecutiveFetchFailures] = useState(0);
  const [lastChangedAtMs, setLastChangedAtMs] = useState(null as number | null);
  const [lastFetchSucceededAtMs, setLastFetchSucceededAtMs] = useState(null as number | null);
  const [nowMs, setNowMs] = useState(Date.now());

  const snapshotRef = useRef(snapshot);
  const logLinesRef = useRef(logLines);
  const signatureRef = useRef(null as string | null);
  const timerRef = useRef(null as number | null);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  useEffect(() => {
    logLinesRef.current = logLines;
  }, [logLines]);

  useEffect(() => {
    let cancelled = false;

    loadRuntimeConfig().then((resolvedConfig) => {
      if (!cancelled) {
        setConfig(resolvedConfig);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (!config) {
      return undefined;
    }

    let cancelled = false;

    const fetchPayload = async (endpoint: string): Promise<RawDashboardPayload | null> => {
      try {
        const response = await fetch(endpoint, { cache: 'no-store' });
        if (!response.ok) {
          return null;
        }
        return (await response.json()) as RawDashboardPayload;
      } catch {
        return null;
      }
    };

    const fetchOnce = async () => {
      if (!config.endpoint) {
        setIsInitialLoading(false);
        return;
      }

      try {
        const rawPayload =
          (await fetchPayload(config.endpoint)) ??
          (config.fallbackEndpoint && config.fallbackEndpoint !== config.endpoint
            ? await fetchPayload(config.fallbackEndpoint)
            : null);

        if (!rawPayload) {
          setConsecutiveFetchFailures((current: number) => current + 1);
          setIsInitialLoading(false);
          return;
        }

        const fetchedAtMs = Date.now();
        setLastFetchSucceededAtMs(fetchedAtMs);
        setConsecutiveFetchFailures(0);

        const normalizedSnapshot = normalizeSnapshot(rawPayload);
        const payloadSignature = JSON.stringify(rawPayload);
        const previousSnapshot = snapshotRef.current;
        const isUnchanged = payloadSignature === signatureRef.current;

        if (isUnchanged) {
          setIsInitialLoading(false);
          return;
        }

        signatureRef.current = payloadSignature;
        setPreviousAgent(
          previousSnapshot.pipeline.currentAgent !== normalizedSnapshot.pipeline.currentAgent
            ? previousSnapshot.pipeline.currentAgent
            : null,
        );
        setSnapshot(normalizedSnapshot);

        const mergedLogs = mergeLogLines(logLinesRef.current, normalizedSnapshot.logLines);
        setLogLines(mergedLogs.lines.length ? mergedLogs.lines : createIdleSnapshot().logLines);

        const nextChangedAt = parseTimestampToMs(normalizedSnapshot.timestamp) ?? Date.now();
        setLastChangedAtMs(nextChangedAt);
        setIsInitialLoading(false);
      } catch {
        setConsecutiveFetchFailures((current: number) => current + 1);
        setIsInitialLoading(false);
      }
    };

    const scheduleLoop = async () => {
      await fetchOnce();
      if (!cancelled) {
        timerRef.current = window.setTimeout(scheduleLoop, config.pollIntervalMs);
      }
    };

    scheduleLoop();

    return () => {
      cancelled = true;
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }
    };
  }, [config]);

  const lastEventAgeSeconds = lastChangedAtMs === null ? null : Math.max(0, Math.floor((nowMs - lastChangedAtMs) / 1000));
  const staleAgeSeconds =
    lastFetchSucceededAtMs === null ? null : Math.max(0, Math.floor((nowMs - lastFetchSucceededAtMs) / 1000));
  const showStaleIndicator = consecutiveFetchFailures >= (config?.staleAfterConsecutiveUnchangedPolls ?? 2);
  const liveSnapshot = withLiveStopwatches(snapshot, nowMs);

  return {
    config,
    snapshot: liveSnapshot,
    logLines,
    previousAgent,
    isInitialLoading,
    showStaleIndicator,
    staleAgeSeconds,
    lastEventAgeSeconds,
  };
}

function shouldAdvanceStopwatches(snapshot: DashboardSnapshot): boolean {
  return snapshot.runtime.processRunning && !snapshot.runtime.paused && !snapshot.runtime.stopRequested;
}

function withLiveStopwatches(snapshot: DashboardSnapshot, nowMs: number): DashboardSnapshot {
  if (!shouldAdvanceStopwatches(snapshot)) {
    return snapshot;
  }

  const snapshotAtMs = parseTimestampToMs(snapshot.timestamp);
  if (snapshotAtMs === null) {
    return snapshot;
  }

  const elapsedDeltaSeconds = Math.max(0, Math.floor((nowMs - snapshotAtMs) / 1000));
  if (elapsedDeltaSeconds <= 0) {
    return snapshot;
  }

  return {
    ...snapshot,
    elapsedSeconds: snapshot.elapsedSeconds + elapsedDeltaSeconds,
    metrics: {
      ...snapshot.metrics,
      modelRuntimeSeconds: snapshot.metrics.modelRuntimeSeconds + elapsedDeltaSeconds,
    },
    runtime: {
      ...snapshot.runtime,
      modelRuntimeSeconds: snapshot.runtime.modelRuntimeSeconds + elapsedDeltaSeconds,
      wallClockElapsedSeconds:
        snapshot.runtime.wallClockElapsedSeconds > 0
          ? snapshot.runtime.wallClockElapsedSeconds + elapsedDeltaSeconds
          : snapshot.runtime.wallClockElapsedSeconds,
    },
  };
}
