# Millrace Mission Control Dashboard

Static React + TypeScript dashboard scaffold for `live.millrace.ai`.

## What is included

- Fullscreen three-zone layout matching the Mission Control frontend spec.
- Dual workshop scenes with crossfade between orchestration and research.
- Horseshoe worker layout with active/idle/completion states.
- Floating task bar with inferred mini pipeline.
- Metrics sidebar with progress heat, commit flash, and test-suite reveal animation.
- Smooth-scrolling log ticker.
- 60-second polling loop with stale-data indicator.
- Runtime config file (`public/config.json`) for the R2 endpoint.
- Three mock telemetry payloads derived from the livestream context:
  - `compiler-run.json`
  - `git-clone-run.json`
  - `cli-harness-run.json`

## Why the telemetry normalization layer exists

The frontend spec’s example payload uses `pipeline.current_agent: "builder"`, while the real Millrace execution and research entrypoints are stage-oriented (`start`, `check`, `goal_intake`, `taskmaster`, etc.).

To keep the dashboard compatible with current Millrace naming and older/preliminary run data, the app normalizes agent aliases such as:

- `builder -> start`
- `qa -> check`
- `articulate -> goal_intake`
- `analyze -> spec_synthesis`
- `clarify -> spec_review`
- `start_large_plan -> start`
- `start_large_execute -> start`
- `reassess -> start`
- `refactor -> start`

## Config

Edit `public/config.json`:

```json
{
  "r2Endpoint": "https://<your-r2-json-url>",
  "pollIntervalMs": 60000,
  "mockMode": "compiler",
  "useMockWhenEndpointMissing": true,
  "staleAfterConsecutiveUnchangedPolls": 2
}
```

Behavior:

- If `r2Endpoint` is set, the app polls that JSON blob.
- If `r2Endpoint` is empty and `useMockWhenEndpointMissing` is `true`, the app loads one of the bundled mock payloads.
- Query overrides are also supported:
  - `?mock=compiler`
  - `?mock=git`
  - `?mock=cli`
  - `?source=https://.../telemetry.json`
  - `?interval=60000`

## Build

```bash
npm install
npm run build
```

This produces a static `dist/` directory ready for Cloudflare Pages.

## Serve locally

```bash
npm run serve
```

## Notes

- React and ReactDOM are loaded from CDN script tags in `public/index.html` to keep the scaffold dependency-light and fully static.
- All animation is CSS-only. The JavaScript runtime only handles polling, diffing, and class/state updates.
