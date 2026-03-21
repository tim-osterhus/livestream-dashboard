# Mission Control Dashboard — Aggregated Log Spec

## Purpose

Define a Codex-only log aggregation path that leaves `research_loop.sh` and `orchestrate_loop.sh` unchanged.

The dashboard pipeline should rely on:

1. Dedicated raw loop logs: `research.log` and `orchestrate.log`
2. One dashboard-side aggregation script that reads those raw logs plus selected Millrace artifacts
3. One sanitized combined output file: `dashboard.log`

The aggregator, not the Millrace loops, owns display formatting, redaction, normalization, and any lightweight derivation needed for the livestream view.

## Constraints

- Do not modify files under `baseline-framework/millrace/` for this feature.
- Scope is Codex-only. Claude/OpenClaw parity is out of scope.
- The aggregator may read Millrace runtime artifacts, but it must not mutate Millrace state.
- The aggregator should be cheap to run continuously on the build machine.
- Pre-livestream setup can include small manual steps. This does not need to be perfectly zero-config.

## Architecture

```text
tmux / shell launch
  ├─ research_loop.sh stdout/stderr  ──► research.log
  ├─ orchestrate_loop.sh stdout/stderr ─► orchestrate.log
  └─ aggregate_logs.py
       ├─ tails both raw logs
       ├─ reads selected Millrace artifacts
       └─ writes dashboard.log

state_sync.py
  └─ tails dashboard.log and emits the public state blob
```

This preserves a clean boundary:

- Millrace loops remain operational/control-plane code.
- Raw logs are private machine-local artifacts.
- `dashboard.log` is the single sanitized public-facing stream.

## Raw Log Creation

The dedicated `research.log` / `orchestrate.log` requirement is satisfied at launch time, not inside the loop scripts.

Recommended options:

1. `tmux pipe-pane`
   - Attach each loop pane to an append-only log file.
   - Best fit when loops already run in tmux.
2. Shell redirection
   - Start each loop with `>> logfile 2>&1`.
   - Simpler for one-off runs.

Example tmux approach:

```bash
tmux pipe-pane -o -t millrace:research 'cat >> /workspace/compiler/_livestream_dashboard/logs/research.log'
tmux pipe-pane -o -t millrace:orchestrate 'cat >> /workspace/compiler/_livestream_dashboard/logs/orchestrate.log'
```

## Aggregator Responsibilities

The new script should live in the dashboard codepath, not in Millrace core. Suggested location:

- `_livestream_dashboard/Livestream_Dashboard/track3/aggregate_logs.py`

Responsibilities:

1. Tail `research.log` and `orchestrate.log` incrementally.
2. Preserve source identity for each line.
3. Sanitize and redact raw output.
4. Keep only useful display lines.
5. Normalize lines into a stable public grammar.
6. Synthesize missing display lines from Millrace artifacts when raw logs are not sufficient.
7. Write one append-only `dashboard.log`.

## Inputs

### Required raw inputs

- `research.log`
- `orchestrate.log`

### Allowed derived-state inputs

These are read-only fallback or enrichment sources:

- `agents/research_state.json`
- `agents/research_events.md`
- `agents/runner_notes.md`
- `agents/tasks.md`
- `agents/tasksbacklog.md`
- `agents/tasksarchive.md`
- `agents/tasksbackburner.md`
- `agents/tasksblocker.md`
- harness summary artifacts such as `summary.tsv` / `summary.json`

The aggregator should prefer raw log lines when they already contain the needed public signal, and only synthesize when the raw stream does not provide a stable enough display event.

## Output Contract

The aggregator writes a single combined sanitized file:

- `dashboard.log`

Each line must follow this shape:

```text
[HH:MM:SS] [ORCH] Stage Builder: starting — model=gpt-5.3-codex task="Implement AST generation"
[HH:MM:SS] [ORCH] Builder: complete
[HH:MM:SS] [ORCH] Progress: 3/18 tasks
[HH:MM:SS] [ORCH] Tokens: in=11832 out=21 cached=5504
[HH:MM:SS] [RES] Stage Incident Resolve: starting — mode=incident model=gpt-5.3-codex
[HH:MM:SS] [RES] Incident Resolve: complete
[HH:MM:SS] [ORCH] Test gcc_torture: passed=312 failed=18 total=1400 active=true
```

Design requirements:

- Timestamp resolution must be seconds.
- Source tag must be `[ORCH]` or `[RES]`.
- Maximum line length: 120 characters after formatting.
- Lines must be safe for public display.

## Public Line Types

The aggregator should emit only these display-level event classes.

### Stage lifecycle

```text
Stage Builder: starting — model=gpt-5.3-codex task="..."
Builder: running
Builder: complete
QA: result=QUICKFIX_NEEDED
Consult: result=NEEDS_RESEARCH
```

### Progress

```text
Progress: 3/18 tasks
```

### Tokens

Codex-only normalized token line:

```text
Tokens: in=11832 out=21 cached=5504
```

`cached` is optional for parser purposes but should be preserved in the log line when available.

### Research mode

```text
Stage Goal Intake: starting — mode=goalspec model=gpt-5.3-codex
Stage Incident Resolve: starting — mode=incident model=gpt-5.3-codex
Stage Audit Validate: starting — mode=audit model=gpt-5.3-codex
```

### Tests

```text
Test gcc_torture: passed=312 failed=18 total=1400 active=true
Test sqlite: passed=0 failed=0 total=0 active=false
```

### Blockers / escalation / errors

```text
Escalation: local recovery exhausted, handing to research loop
Task blocked: missing dependency
Warning: QA failed with exit=1
```

## Sanitization Rules

### Keep

- Stage start/running/complete events
- QA/status/result lines
- Progress lines
- Token usage lines
- Test result lines
- Research-mode lines
- Escalation/blocker/error lines

### Strip

- Prompt bodies
- Model instructions
- Agent prose output
- Stack traces unless reduced to a short warning/error summary
- Full file paths
- URLs
- Secrets, tokens, credentials, cookies, auth headers

### Normalize

- Agent filenames to display names
- Dates down to `HH:MM:SS`
- Whitespace and punctuation
- Status vocabulary into one stable grammar

## Derivation Rules

The aggregator is allowed to synthesize display lines from Millrace artifacts.

### Active loop

Derived from the raw source file being tailed.

- `orchestrate.log` => orchestration
- `research.log` => research

No extra Millrace line is required.

### Research mode

Priority order:

1. Explicit `mode=` already present on a research stage line
2. `agents/research_state.json`
3. `MODE_DISPATCH` entries in `agents/research_events.md`
4. Final fallback: infer from the research agent identity

### Current model

Priority order:

1. `model=...` already present in a stage-start line
2. Recent Codex token or runner-note artifact associated with the same stage
3. If unavailable, omit from the display line rather than inventing a value

### Task name

Priority order:

1. `task="..."` already present in a stage-start line
2. Current active card title in `agents/tasks.md`

### Current task index / total

For dashboard purposes, `total_tasks` may be a live snapshot rather than an immutable original denominator.

Recommended policy:

```text
total_tasks =
  count(active task in tasks.md, if present) +
  count(pending cards in tasksbacklog.md) +
  count(completed cards in tasksarchive.md)
```

This matches the user’s current desired behavior and is sufficient for livestream display.

`current_task_index` should be derived from:

- progress lines when present, otherwise
- `completed count + active slot` from the task stores

### Token usage

Codex-only source of truth:

- existing `Token usage:` lines already written by the loops

The aggregator should rewrite them into one display format:

```text
Tokens: in=... out=... cached=...
```

If a raw token line is malformed or missing, do not invent counts.

### Test results

Priority order:

1. Parseable suite lines already present in the orchestration raw log
2. Harness summary artifacts if the raw log is not stable enough

The aggregator should emit one public line per suite so the dashboard does not need to parse raw harness output.

### Escalations / blockers

Priority order:

1. Clear raw log line if present
2. `agents/runner_notes.md`
3. `agents/tasksblocker.md`
4. `agents/tasksbackburner.md`
5. `agents/research_events.md`

These may be emitted as synthetic one-line summaries when needed.

## Runtime Behavior

The aggregator should run as a small polling tailer.

Recommended behavior:

1. Poll both raw logs every 1 second.
2. Track offsets and inode changes.
3. Handle truncation and rotation cleanly.
4. Parse only new raw lines.
5. Optionally poll artifact files on each cycle or on a slightly slower interval such as every 2-5 seconds.
6. Append newly accepted or synthesized public lines to `dashboard.log`.
7. De-duplicate synthetic lines so unchanged state does not spam the ticker.

Append-only output is acceptable. A reset option may be provided for pre-show cleanup.

## CLI / Config

Suggested interface:

```bash
python3 aggregate_logs.py \
  --research-log /workspace/compiler/_livestream_dashboard/logs/research.log \
  --orchestrate-log /workspace/compiler/_livestream_dashboard/logs/orchestrate.log \
  --repo-root /workspace/compiler \
  --dashboard-log /workspace/compiler/_livestream_dashboard/logs/dashboard.log \
  --check-interval 1
```

Suggested options:

- `--research-log`
- `--orchestrate-log`
- `--dashboard-log`
- `--repo-root`
- `--check-interval`
- `--reset-output-on-start`
- `--once`

## Relationship To Existing Track 3 Code

This spec should align with the existing parser expectations in:

- `_livestream_dashboard/Livestream_Dashboard/track3/log_aggregator.py`
- `_livestream_dashboard/Livestream_Dashboard/track3/state_sync.py`

Implementation guidance:

- Reuse the current `log_aggregator.py` structure rather than starting over.
- Extend it so it can synthesize stable dashboard lines from Millrace artifacts when raw logs alone are insufficient.
- Keep the line grammar compatible with `state_sync.py`.
- Prefer changing the aggregator over changing `state_sync.py` unless parser compatibility clearly requires it.

## Testing Requirements

Testing should be dashboard-side and read-only with respect to Millrace control code.

### Unit coverage

- raw stage-start normalization
- raw status normalization
- token line normalization
- path/URL/secret redaction
- timestamp extraction
- truncation to 120 chars
- artifact-derived research-mode emission
- artifact-derived progress synthesis
- artifact-derived test-suite emission
- synthetic-line de-duplication

### Fixture coverage

Use mixed fixtures containing:

- realistic orchestration raw log snippets
- realistic research raw log snippets
- Codex token lines
- noisy irrelevant lines that must be dropped
- malformed token/status lines
- research-state and runner-note artifact samples
- task-store snapshots for progress derivation
- harness summary samples for suite derivation

### Integration coverage

1. Raw logs only
   - aggregator outputs correct combined display lines
2. Raw logs plus artifact enrichment
   - missing mode/progress/test lines are synthesized correctly
3. Restart behavior
   - truncation/rotation does not corrupt output
4. Safety
   - secrets and private paths never appear in `dashboard.log`

## Acceptance Criteria

This feature is complete when:

1. `research.log` and `orchestrate.log` can be produced without modifying either loop script.
2. One aggregator script can turn those raw logs into a stable public `dashboard.log`.
3. The output is sufficient for `state_sync.py` to populate the mission-control blob for Codex runs.
4. Research mode, task progress, task names, token usage, and test-suite lines can be shown even when some of them must be derived from Millrace artifacts rather than raw loop logs alone.
5. All sanitation/redaction guarantees hold under noisy real-world logs.

## Non-Goals

- Modifying `research_loop.sh`
- Modifying `orchestrate_loop.sh`
- Supporting non-Codex runners
- Turning the aggregator into a second orchestration system
- Making `total_tasks` semantically immutable across dynamic backlog changes
