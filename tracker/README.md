# Livestream tracker: log aggregator + state sync

This folder contains a concrete implementation of the two-script tracker from `track3-state-sync-spec-v2.md`:

- `log_aggregator.py`
- `state_sync.py`

The implementation stays standard-library-only and is designed to be cheap enough to run continuously during long Millrace livestreams.

## What I optimized for

The livestream plan and the two preliminary runs make the tracker needs pretty clear:

- it has to be **generic across multiple run types** rather than compiler-only,
- it has to be **simple and legible** because the build itself is the main event,
- it has to be **low-overhead** because long runs and tight token/runtime budgets matter,
- and it has to tolerate real autonomy-loop messiness instead of assuming a pristine final log format.

That is why the code is built around:

- tolerant pattern matching,
- append-only tailing with offset tracking,
- no extra dependencies,
- idempotent replay on the state parser,
- and configuration flags for the places where the written spec contradicts itself or leaves important details open.

## Files

### `log_aggregator.py`

Reads:

- `research.log`
- `orchestrate.log`
- selected repo-local Millrace artifacts via `--repo-root` when raw logs do not contain display-ready task/mode/test metadata

Writes:

- `dashboard.log`

Responsibilities:

- tail both raw logs using offsets,
- wait for files that do not exist yet,
- recover from truncate/rotation,
- keep only publicly safe lines,
- normalize agent names,
- normalize Codex token lines into `Tokens: in=... out=... cached=...`,
- derive `Progress: N/M tasks` from task-store state when needed,
- enrich research stage starts with `mode=...`,
- emit parseable suite summaries from `summary.json` when available,
- redact paths/URLs/secrets,
- format public-facing dashboard lines.

### `state_sync.py`

Reads:

- `dashboard.log`

Produces:

- in-memory state blob,
- optional stdout JSON for debugging,
- PUT/POST upload to your R2 endpoint.

Responsibilities:

- parse state incrementally,
- remain idempotent on replayed/duplicated dashboard lines,
- infer current task/task list/model/tokens/research mode,
- attach latest git commit metadata,
- upload every cycle.

## Quick start

### Compiler run example

```bash
python3 log_aggregator.py \
  --research-log ./research.log \
  --orchestrate-log ./orchestrate.log \
  --repo-root /path/to/project/repo \
  --dashboard-log ./dashboard.log
```

```bash
python3 state_sync.py \
  --dashboard-log ./dashboard.log \
  --repo-path /path/to/project/repo \
  --run-id compiler-run-001 \
  --r2-endpoint 'https://your-endpoint.example/state.json'
```

### Git clone prelim example

```bash
python3 state_sync.py \
  --dashboard-log ./dashboard.log \
  --repo-path /path/to/git-clone-repo \
  --run-id git-run-001 \
  --test-suites compat_git,blind_qa \
  --r2-endpoint 'https://your-endpoint.example/state.json'
```

### CLI harness prelim example

```bash
python3 state_sync.py \
  --dashboard-log ./dashboard.log \
  --repo-path /path/to/cli-harness-repo \
  --run-id cli-run-001 \
  --test-suites provider_openai,provider_anthropic,provider_google,e2e_task \
  --r2-endpoint 'https://your-endpoint.example/state.json'
```

## Debug / local validation

One-pass aggregation:

```bash
python3 log_aggregator.py \
  --research-log ./mock_research.log \
  --orchestrate-log ./mock_orchestrate.log \
  --repo-root /path/to/repo \
  --dashboard-log ./dashboard.log \
  --reset-output-on-start \
  --once
```

One-pass state build with no upload:

```bash
python3 state_sync.py \
  --dashboard-log ./dashboard.log \
  --repo-path /path/to/repo \
  --run-id test-run \
  --once --dry-run --stdout-json
```

Write a local JSON blob for the MVP dashboard and skip upload:

```bash
python3 state_sync.py \
  --dashboard-log ./dashboard.log \
  --repo-path /path/to/repo \
  --run-id test-run \
  --output-json ../workspace/millrace-live-dashboard/dist/state/live-state.json \
  --dry-run
```

## Main assumptions and ambiguities

These are the places where the spec is incomplete or internally inconsistent, plus the exact best-guess behavior I chose.

### 1) Raw loop log format is not finalized

**Ambiguity**

The spec explicitly says the real parsing patterns will need refinement after a test run. That means the raw logs are not yet a stable contract.

**What I implemented**

The aggregator uses a whitelist-style keep filter and tolerant regexes for:

- stage start/running/complete lines,
- explicit status lines,
- progress lines,
- token lines,
- error/escalation lines,
- test/suite lines.

Anything outside those shapes is dropped by default.

**How to change it**

Edit these constants near the top of `log_aggregator.py`:

- `KEEP_PATTERNS`
- `STATUS_LINE_RE`
- `STAGE_LINE_RE`
- `SIMPLE_AGENT_EVENT_RE`
- `EXIT_ONLY_RE`

If your real loop logs use different verbs or prefixes, that is the first place to tune.

### 2) Dashboard restart behavior is underspecified

**Ambiguity**

The spec says the aggregator should re-read raw logs from the beginning and regenerate `dashboard.log`, but it also says duplicate lines are acceptable.

Those two statements imply different restart behaviors:

- truncate and fully rebuild output, or
- append duplicates and rely on an idempotent parser later.

**What I implemented**

Default behavior is append-only recovery because it is simpler and safer during a live run.

If the process restarts and starts reading raw logs from offset 0 again, it can append duplicates to `dashboard.log`.

The state parser deduplicates exact repeated dashboard lines so the state stays stable.

**How to change it**

Set either:

- `RESET_OUTPUT_ON_START=1`, or
- pass `--reset-output-on-start`

That truncates `dashboard.log` before the aggregator starts writing.

### 3) Chronological ordering across two tailed files is not perfectly solvable without buffering

**Ambiguity**

The spec wants the combined output interleaved chronologically, but the tracker is reading two independently flushed files on a polling loop.

A line with an older timestamp can arrive late.

**What I implemented**

The aggregator sorts new lines per poll batch before writing them.

That gives correct ordering for most real cases with almost no overhead.

**What it does not do**

It does not maintain a long-lived reorder buffer across poll cycles.

**How to change it**

If you observe frequent out-of-order flushes, add a small holdback buffer in `Aggregator.process_cycle()` and only flush events older than N seconds.

That would improve ordering at the cost of slightly delayed dashboard updates.

### 4) `dashboard.log` only preserves `HH:MM:SS`, but the state blob needs full timestamps

**Ambiguity**

The spec requires ISO timestamps such as `agent_started_at`, but the dashboard line format strips the date and keeps only `HH:MM:SS`.

**What I implemented**

`state_sync.py` reconstructs dates using:

- a configurable tracker timezone,
- the dashboard file mtime as the initial anchor date,
- midnight-rollover detection when time moves backward by more than 12 hours.

Default timezone is `UTC` because the spec examples emit `Z` timestamps.

**How to change it**

Set:

```bash
TRACKER_TZ=Pacific/Honolulu
```

or another IANA zone.

If your raw logs already use UTC, leave the default alone.

If you later decide the state blob should use build-machine local time instead of UTC-normalized ISO, the code to change is:

- `_resolve_event_datetime()`
- `_build_state_blob()`

inside `state_sync.py`.

### 5) `pipeline.current_agent` is inconsistent inside the spec

**Ambiguity**

The JSON example uses values like:

- `builder`

But the field-derivation table says the stored values should be:

- `start`
- `check`
- `integrate`
- etc.

**What I implemented**

Default behavior follows the field-derivation table:

- `Builder -> start`
- `QA -> check`
- `Integrator -> integrate`

**How to change it**

If your frontend already expects `builder` / `qa` style values, run with:

```bash
AGENT_VALUE_STYLE=friendly
```

or:

```bash
python3 state_sync.py --agent-value-style friendly ...
```

The mappings live here:

- `DISPLAY_AGENT_TO_BLOB`
- `DISPLAY_AGENT_TO_FRIENDLY`

### 6) The current task index is only partially explicit in the public log

**Ambiguity**

The spec example shows:

- progress line `2/18`
- then a Builder start for task 3
- then `current_task_index = 3`

But the spec also says current task index comes from progress lines.

Those two rules do not fully agree.

**What I implemented**

Best guess:

- `Progress: 2/18 tasks` means 2 tasks are complete.
- `Stage Builder: starting` means the next active task is `completed + 1`.
- if the builder start includes `task="..."`, that name is bound to the inferred task index.

This matches the example behavior.

**How to change it**

If your real loop logs emit explicit task indices, update:

- `PROGRESS_RE`
- `_parse_stage_start()`
- `_infer_next_task_index()`

in `state_sync.py` to trust the explicit index instead of inference.

### 7) Token lines may be deltas or cumulative totals

**Ambiguity**

The spec says token lines might be per-stage or cumulative.

**What I implemented**

The parser treats token lines as **absolute totals** if they contain words like:

- `cumulative`
- `running total`
- `overall`
- `lifetime`
- `so far`

Otherwise it treats them as per-stage deltas and adds them to the running totals.

**How to change it**

Update:

- `TOKEN_RE`
- the `is_absolute` heuristic in `_parse_tokens()`

inside `state_sync.py`.

### 8) Test suites are compiler-centric in the spec, but the tracker needs to cover all livestreams

**Ambiguity**

The spec’s `tests` object is oriented around compiler validation:

- `gcc_torture`
- `sqlite`
- `redis`
- `lua`

That makes sense for the compiler livestream, but not for the Git clone or CLI harness prelim runs.

**What I implemented**

Default test-suite keys follow the spec.

But the script lets you override them per run using:

```bash
TRACKER_TEST_SUITES=compat_git,blind_qa
```

or the CLI equivalent.

It also dynamically adds new suites if it sees structured test lines for names that were not predeclared.

**How to change it**

- Set `TRACKER_TEST_SUITES`
- or edit `DEFAULT_TEST_SUITES`
- or tighten the regexes `TEST_STRUCTURED_RE` / `TEST_FREEFORM_RE`

### 9) Path stripping is only a best guess until you see live logs

**Ambiguity**

The spec says to strip internal framework references and directory structure, but it does not define the exact raw path shapes that will appear.

**What I implemented**

The aggregator redacts:

- absolute file-system paths,
- `agents/...` internal references,
- URLs.

**How to change it**

Tune these regexes in `log_aggregator.py`:

- `ABSOLUTE_PATH_RE`
- `INTERNAL_PATH_RE`
- `URL_RE`

If your logs use Windows paths, tmux paths, temp dirs, or runner-specific bundles in a different format, expand those regexes.

### 10) State replay idempotency vs. exact dashboard fidelity

**Ambiguity**

The spec wants replay-safe reconstruction after a crash, but the dashboard itself can contain duplicate lines after aggregator restart.

**What I implemented**

The state parser deduplicates exact repeated dashboard lines for state transitions, but it keeps the literal last `N` dashboard lines in `log_lines` so the public feed still reflects what was actually written.

**How to change it**

If you want `log_lines` to also suppress duplicates, change `_ingest_new_dashboard_lines()` so it appends to `self.state.log_lines` only after the fingerprint check.

## Where to tune the parser after the first real run

Once you have 5-10 minutes of actual `research.log` and `orchestrate.log`, do this:

1. compare raw lines against `KEEP_PATTERNS` in `log_aggregator.py`
2. refine agent-name normalization in `RAW_AGENT_TO_DISPLAY`
3. verify whether the loop emits explicit task names and/or indices
4. confirm the token-line format and tighten `TOKEN_RE`
5. confirm whether logs are UTC or local time and set `TRACKER_TZ`
6. confirm whether your frontend wants `start/check` or `builder/qa`

## Minimal deployment notes

For live usage, run the aggregator first, then state sync, as separate long-lived processes.

A simple tmux setup is enough. No framework or process manager is required.
