# Livestream Dashboard

This repo is the standalone dashboard package for `live.millrace.ai`.

## Layout

- `site/`
  - static frontend
  - polls a JSON blob and renders the dashboard
- `tracker/`
  - `log_aggregator.py` merges `research.log` + `orchestrate.log` into one public `dashboard.log`
  - `state_sync.py` converts `dashboard.log` into `live-state.json`
- `scripts/`
  - local launch helpers
- `reference/`
  - copied specs and checklist docs
- `runtime/`
  - local logs produced by the launcher

## Runtime model

The browser app should not read the two raw loop logs directly.

The intended flow is:

1. Millrace writes `research.log` and `orchestrate.log`
2. `tracker/log_aggregator.py` emits `runtime/dashboard.log`
3. `tracker/state_sync.py` emits `site/dist/state/live-state.json` or uploads to an endpoint
4. the frontend polls the JSON blob

## Local launch

To run the full local stack against the current prelim workspace:

```bash
bash ./scripts/run_dashboard_stack.sh /mnt/f/_prelim-run/git-build
```

That script will:

- install frontend dependencies if needed
- build the site
- serve `site/dist`
- run the log aggregator
- run the state sync writer

## Frontend refresh model

The frontend polls the JSON endpoint on a timer with `cache: no-store`.
It updates automatically; the viewer does not need to manually refresh the page.
