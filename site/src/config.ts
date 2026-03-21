import type { ResolvedConfig, RuntimeConfig } from './types.js';

const DEFAULT_POLL_INTERVAL_MS = 60_000;
const DEFAULT_STALE_POLLS = 2;

function normalizeMockMode(value: string | null): string {
  switch ((value || '').toLowerCase()) {
    case 'git':
    case 'git-clone':
    case 'git_clone':
      return 'git-clone';
    case 'cli':
    case 'cli-harness':
    case 'cli_harness':
      return 'cli-harness';
    case 'compiler':
    default:
      return 'compiler';
  }
}

function toResolvedConfig(raw: RuntimeConfig, searchParams: URLSearchParams): ResolvedConfig {
  const sourceOverride = searchParams.get('source');
  const mockOverride = searchParams.get('mock');
  const pollOverride = searchParams.get('interval');
  const mockMode = normalizeMockMode(mockOverride || raw.mockMode || 'compiler');
  const fallbackEndpoint = raw.useMockWhenEndpointMissing !== false ? `./mock/${mockMode}-run.json` : null;
  const pollIntervalMs = Math.max(5_000, Number.parseInt(pollOverride ?? '', 10) || raw.pollIntervalMs || DEFAULT_POLL_INTERVAL_MS);
  const staleAfterConsecutiveUnchangedPolls = Math.max(
    1,
    raw.staleAfterConsecutiveUnchangedPolls ?? DEFAULT_STALE_POLLS,
  );

  if (sourceOverride) {
    return {
      endpoint: sourceOverride,
      fallbackEndpoint,
      endpointLabel: sourceOverride,
      pollIntervalMs,
      staleAfterConsecutiveUnchangedPolls,
    };
  }

  if (raw.r2Endpoint && raw.r2Endpoint.trim()) {
    return {
      endpoint: raw.r2Endpoint,
      fallbackEndpoint,
      endpointLabel: raw.r2Endpoint,
      pollIntervalMs,
      staleAfterConsecutiveUnchangedPolls,
    };
  }

  if (fallbackEndpoint) {
    return {
      endpoint: fallbackEndpoint,
      fallbackEndpoint,
      endpointLabel: `mock:${mockMode}`,
      pollIntervalMs,
      staleAfterConsecutiveUnchangedPolls,
    };
  }

  return {
    endpoint: null,
    fallbackEndpoint: null,
    endpointLabel: 'idle',
    pollIntervalMs,
    staleAfterConsecutiveUnchangedPolls,
  };
}

export async function loadRuntimeConfig(): Promise<ResolvedConfig> {
  const searchParams = new URLSearchParams(window.location.search);

  try {
    const response = await fetch('./config.json', { cache: 'no-store' });
    if (response.ok) {
      const rawConfig = (await response.json()) as RuntimeConfig;
      return toResolvedConfig(rawConfig, searchParams);
    }
  } catch {
    // fall through to defaults
  }

  return toResolvedConfig({}, searchParams);
}
