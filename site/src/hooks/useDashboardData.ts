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
}

export function useDashboardData(): DashboardDataState {
  const [config, setConfig] = useState(null as ResolvedConfig | null);
  const [snapshot, setSnapshot] = useState(createIdleSnapshot() as DashboardSnapshot);
  const [logLines, setLogLines] = useState(createIdleSnapshot().logLines as string[]);
  const [previousAgent, setPreviousAgent] = useState(null as CanonicalAgent | null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [consecutiveUnchangedPolls, setConsecutiveUnchangedPolls] = useState(0);
  const [lastChangedAtMs, setLastChangedAtMs] = useState(null as number | null);
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
          setIsInitialLoading(false);
          return;
        }

        const normalizedSnapshot = normalizeSnapshot(rawPayload);
        const payloadSignature = JSON.stringify(rawPayload);
        const previousSnapshot = snapshotRef.current;
        const previousTimestamp = previousSnapshot.timestamp;
        const isUnchanged =
          payloadSignature === signatureRef.current ||
          (normalizedSnapshot.timestamp !== null && normalizedSnapshot.timestamp === previousTimestamp);

        if (isUnchanged) {
          setConsecutiveUnchangedPolls((current: number) => current + 1);
          setIsInitialLoading(false);
          return;
        }

        signatureRef.current = payloadSignature;
        setConsecutiveUnchangedPolls(0);
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

  const staleAgeSeconds = lastChangedAtMs === null ? null : Math.max(0, Math.floor((nowMs - lastChangedAtMs) / 1000));
  const showStaleIndicator =
    lastChangedAtMs !== null &&
    consecutiveUnchangedPolls >= (config?.staleAfterConsecutiveUnchangedPolls ?? 2);

  return {
    config,
    snapshot,
    logLines,
    previousAgent,
    isInitialLoading,
    showStaleIndicator,
    staleAgeSeconds,
  };
}
