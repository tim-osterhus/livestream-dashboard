# Mission Control Dashboard — State-Sync & Log Aggregator Spec

## What This Is

Two lightweight local scripts that run on the build machine alongside a Millrace autonomous build:

1. **Log Aggregator** (`log_aggregator.py`) — Tails both the orchestration log and research log, sanitizes/formats lines, labels each with its source loop, and writes to a single combined dashboard log file.
2. **State-Sync** (`state_sync.py`) — Tails the aggregated dashboard log, parses current state into a JSON blob, and POSTs that blob to Cloudflare R2 every 60 seconds.

Together, these are the only bridge between the build machine and the public dashboard. They must be simple, reliable, and impose zero meaningful overhead on the build process.

---

## Architecture

```
research_loop.sh ──► research.log ──┐
                                     ├──► log_aggregator.py ──► dashboard.log
orchestrate_loop.sh ──► orchestrate.log ──┘
                                                    │
                                          state_sync.py tails this
                                                    │
                                              JSON blob POST ──► Cloudflare R2
```

### Why Two Scripts Instead of One

Separation of concerns. The aggregator owns sanitization, formatting, and source labeling — deciding what the public sees. The state-sync script owns state parsing and upload — turning clean log lines into structured JSON. This means:

- Sanitization rules can be changed without touching the upload logic.
- Log formatting can be customized per-source (different inclusion rules for research vs. orchestration) without complicating the state parser.
- The raw loop logs are never read by anything that touches the network. Only the pre-cleaned dashboard log leaves the machine.
- Each script can be tested independently — the aggregator against raw logs, the state-sync against a mock dashboard log.

---

## Script 1: Log Aggregator

### Input

Two raw log files written by the Millrace loop scripts:

| File | Source | Written By |
|------|--------|------------|
| `research.log` | Research loop events | `research_loop.sh` |
| `orchestrate.log` | Orchestration loop events | `orchestrate_loop.sh` |

### Output

A single combined log file (`dashboard.log`) containing sanitized, formatted, source-labeled lines ready for public display.

### Line Format

Every line in `dashboard.log` follows this format:

```
[HH:MM:SS] [ORCH] Stage Builder: starting — model=gpt-5.2
[HH:MM:SS] [ORCH] Builder: complete
[HH:MM:SS] [ORCH] Stage QA: starting — model=gpt-5.2
[HH:MM:SS] [RES]  Stage Spec Synthesis: starting — mode=goalspec
[HH:MM:SS] [RES]  Critic: complete
[HH:MM:SS] [ORCH] Progress: 2/18 tasks — elapsed 04h12m
[HH:MM:SS] [ORCH] Tokens: in=245000 out=62000 (stage total)
```

- Timestamp: time only, `[HH:MM:SS]`, extracted from the raw log line or generated at aggregation time.
- Source tag: `[ORCH]` or `[RES]` with padding so columns align.
- Content: sanitized event text.
- Max line length: 120 characters (truncated with ellipsis if exceeded).

### Sanitization Rules

**Keep:**
- Stage transition events: `Stage Builder: starting`, `QA: complete`, etc.
- Completion statuses: `QUICKFIX_NEEDED`, `BLOCKED`, `QA_COMPLETE`, etc.
- Progress summaries: `Progress: 2/18 tasks — elapsed 04h12m`
- Timing information: elapsed seconds, stage durations
- Model and runner metadata: `model=gpt-5.2`
- Error/escalation events
- Token usage lines emitted by the loop scripts
- Research mode indicators (GoalSpec, Incident, Audit)

**Strip:**
- Any raw LLM prompt content or agent system instructions
- Internal Millrace framework references (file paths, config values, internal state markers)
- File paths that reveal directory structure (e.g., `/home/user/millrace/agents/...`)
- Raw LLM output or response content
- Any line containing API keys, tokens, or credentials

**Normalize:**
- Agent names: `_start.md` → `Builder`, `_check.md` → `QA`, etc. (see Agent Name Mapping below)
- Timestamps: strip date portion, keep `HH:MM:SS` only
- Truncate lines to 120 chars max after formatting

### Agent Name Mapping

The aggregator normalizes raw agent references to display-friendly names:

| Raw Reference | Display Name |
|---------------|-------------|
| `_start.md` | Builder |
| `_integrate.md` | Integrator |
| `_check.md` | QA |
| `_hotfix.md` | Hotfix |
| `_doublecheck.md` | Doublecheck |
| `_consult.md` | Consult |
| `_troubleshoot.md` | Troubleshoot |
| `_update.md` | Update |
| `_goal_intake.md` | Goal Intake |
| `_spec_synthesis.md` | Spec Synthesis |
| `_spec_review.md` | Spec Review |
| `_critic.md` | Critic |
| `_designer.md` | Designer |
| `_taskmaster.md` | Taskmaster |
| `_taskaudit.md` | Task Audit |
| `_objective_profile_sync.md` | Objective Sync |
| `_mechanic.md` | Mechanic |
| `_incident_intake.md` | Incident Intake |
| `_incident_resolve.md` | Incident Resolve |
| `_incident_archive.md` | Incident Archive |
| `_contractor.md` | Contractor |
| `_audit_intake.md` | Audit Intake |
| `_audit_validate.md` | Audit Validate |
| `_audit_gatekeeper.md` | Audit Gatekeeper |

This mapping will need refinement once real log output is available. The raw logs may use filenames, display names, or shorthand.

### Runtime Behavior

- Tail both input files simultaneously (using file offsets, not re-reading).
- On each check (~1-2 second interval), read new lines from both files.
- For each new line: determine if it passes the keep/strip rules, apply formatting, write to `dashboard.log`.
- If an input file doesn't exist yet, wait and poll for its creation.
- If an input file is truncated/rotated, reset its read offset.
- Lines from both sources are interleaved chronologically based on their timestamps.

### Configuration

| Parameter | Description | Example |
|-----------|-------------|---------|
| `RESEARCH_LOG` | Path to research loop log file | `./research.log` |
| `ORCHESTRATE_LOG` | Path to orchestration loop log file | `./orchestrate.log` |
| `DASHBOARD_LOG` | Path to output dashboard log file | `./dashboard.log` |
| `CHECK_INTERVAL` | Seconds between tail checks (default: 1) | `1` |

### Estimated Size

~80-120 lines of Python. This is a small script — the complexity is in the sanitization rules, not the architecture.

---

## Script 2: State-Sync

### Input

The aggregated `dashboard.log` file produced by the log aggregator.

### Output

A JSON blob (~2-5KB) POSTed to Cloudflare R2 every 60 seconds.

### JSON Blob Schema

```json
{
  "timestamp": "2026-03-20T14:56:47Z",
  "run_id": "compiler-run-001",
  "elapsed_seconds": 14400,

  "loop": {
    "active_loop": "orchestration",
    "research_mode": null
  },

  "pipeline": {
    "current_agent": "builder",
    "current_task_index": 3,
    "total_tasks": 18,
    "agent_started_at": "2026-03-20T14:50:25Z"
  },

  "tasks": [
    {
      "id": 1,
      "name": "Implement lexer and tokenizer",
      "status": "complete"
    },
    {
      "id": 2,
      "name": "Build recursive descent parser",
      "status": "complete"
    },
    {
      "id": 3,
      "name": "Implement AST generation",
      "status": "active",
      "active_agent": "builder"
    },
    {
      "id": 4,
      "name": "Build type checker",
      "status": "pending"
    }
  ],

  "metrics": {
    "tokens_in": 12450000,
    "tokens_out": 3200000,
    "current_model": "gpt-5.2",
    "cycle_number": 14
  },

  "tests": {
    "gcc_torture": { "passed": 312, "failed": 18, "total": 1400 },
    "sqlite": { "passed": 0, "failed": 0, "total": 0, "active": false },
    "redis": { "passed": 0, "failed": 0, "total": 0, "active": false },
    "lua": { "passed": 0, "failed": 0, "total": 0, "active": false }
  },

  "latest_commit": {
    "hash": "a1b2c3d",
    "message": "Implement x86 register allocation for binary ops",
    "timestamp": "2026-03-20T14:48:00Z"
  },

  "log_lines": [
    "[14:35:12] [ORCH] Builder: complete",
    "[14:35:12] [ORCH] Stage QA: starting — model=gpt-5.2",
    "[14:42:58] [ORCH] QA: result=QUICKFIX_NEEDED",
    "[14:43:01] [ORCH] Stage Hotfix: starting",
    "[14:50:22] [ORCH] Hotfix: complete",
    "[14:50:22] [ORCH] Progress: 2/18 tasks — elapsed 04h12m",
    "[14:50:25] [ORCH] Stage Builder: starting — task=\"Implement AST generation\"",
    "[14:56:47] [ORCH] Stage Builder: running (382s elapsed)"
  ]
}
```

---

## Field Derivation

The state-sync script parses `dashboard.log` (which is already sanitized and formatted by the aggregator). All field values are derived from the pre-cleaned lines.

### `timestamp`
Current UTC time at the moment of each sync cycle. ISO 8601 format.

### `run_id`
Static string, set via config or command-line argument at script start. Does not change during a run.

### `elapsed_seconds`
Wall-clock seconds since the first non-idle log event was observed. The script records the timestamp of the first real stage event and computes elapsed from there.

### `loop.active_loop`
Derived from the source tag on recent lines:
- If the most recent stage events are tagged `[ORCH]`, set to `"orchestration"`.
- If the most recent stage events are tagged `[RES]`, set to `"research"`.

### `loop.research_mode`
`null` when `active_loop` is `"orchestration"`. When research is active, derived from agent display names in `[RES]` lines:
- Goal Intake, Spec Synthesis, Spec Review, Critic, Designer, Taskmaster, Task Audit, Objective Sync → `"goalspec"`
- Incident Intake, Incident Resolve, Incident Archive → `"incident"`
- Contractor, Audit Intake, Audit Validate, Audit Gatekeeper → `"audit"`
- Mechanic can appear in any mode — does not change the current `research_mode`
- Taskmaster and Task Audit can appear in goalspec or incident — does not change mode on their own

### `pipeline.current_agent`
The agent name extracted from the most recent `Stage X: starting` line in the dashboard log. Stored as the blob-format short name:

| Display Name (from aggregator) | Blob Value |
|-------------------------------|------------|
| Builder | `start` |
| Integrator | `integrate` |
| QA | `check` |
| Hotfix | `hotfix` |
| Doublecheck | `doublecheck` |
| Consult | `consult` |
| Troubleshoot | `troubleshoot` |
| Update | `update` |
| Goal Intake | `goal_intake` |
| Spec Synthesis | `spec_synthesis` |
| Spec Review | `spec_review` |
| Critic | `critic` |
| Designer | `designer` |
| Taskmaster | `taskmaster` |
| Task Audit | `taskaudit` |
| Objective Sync | `objective_profile_sync` |
| Mechanic | `mechanic` |
| Incident Intake | `incident_intake` |
| Incident Resolve | `incident_resolve` |
| Incident Archive | `incident_archive` |
| Contractor | `contractor` |
| Audit Intake | `audit_intake` |
| Audit Validate | `audit_validate` |
| Audit Gatekeeper | `audit_gatekeeper` |

### `pipeline.current_task_index` and `total_tasks`
Parsed from progress summary lines (e.g., `Progress: 2/18 tasks`). Updated whenever a new progress event appears.

### `pipeline.agent_started_at`
Timestamp extracted from the most recent `Stage X: starting` line.

### `tasks`
Derived from progress events and task-start events:
1. Task names from task-start events in the log.
2. Status inferred from current task index: below = `"complete"`, at = `"active"`, above = `"pending"`.
3. Unknown pending task names use `"Pending task N"` as placeholder.

### `metrics.tokens_in` and `metrics.tokens_out`
Running totals parsed from token usage lines in the dashboard log. The loop scripts emit token counts per stage (e.g., `Tokens: in=245000 out=62000`). The state-sync script accumulates these into running totals.

If a stage's token line includes a cumulative total rather than a per-stage delta, use that directly instead of summing.

### `metrics.current_model`
Parsed from stage-start events that include model information (e.g., `model=gpt-5.2`).

### `metrics.cycle_number`
Running count of completed tasks. Incremented each time a task transitions to complete based on progress events.

### `tests`
Parsed from test execution output lines if/when the orchestration loop runs validation suites. Until testing begins, all values are 0 with `active: false`.

### `latest_commit`
Obtained by running `git log -1 --format="%H|%s|%aI"` against the project repository on each sync cycle. Split on `|` to extract hash, message, and timestamp.

### `log_lines`
The last 8-10 lines from `dashboard.log`, taken verbatim. These are already sanitized, formatted, and source-labeled by the aggregator. The state-sync script does NOT modify them — just includes the most recent lines as-is.

---

## Upload

### Target
Cloudflare R2 bucket, accessed via either:
- A presigned PUT URL (simplest — generate once, valid for the duration of the run), or
- A Cloudflare Workers proxy endpoint that accepts the JSON body and writes to R2

The R2 object key should be fixed (e.g., `state.json`) so the frontend always polls the same URL.

### Method
HTTP PUT or POST of the serialized JSON body. Content-Type: `application/json`.

### Frequency
Every 60 seconds, unconditionally. Even if nothing has changed — the timestamp update itself signals liveness.

### Error Handling
- If the upload fails, log a warning locally and retry once after 5 seconds.
- If the retry also fails, skip this cycle and try again in 60 seconds.
- Never block or crash on upload failure. The build must continue regardless.

---

## Configuration

### Log Aggregator (`log_aggregator.py`)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `RESEARCH_LOG` | Path to research loop log file | `./research.log` |
| `ORCHESTRATE_LOG` | Path to orchestration loop log file | `./orchestrate.log` |
| `DASHBOARD_LOG` | Path to output dashboard log file | `./dashboard.log` |
| `CHECK_INTERVAL` | Seconds between tail checks (default: 1) | `1` |

### State-Sync (`state_sync.py`)

| Parameter | Description | Example |
|-----------|-------------|---------|
| `DASHBOARD_LOG` | Path to aggregated dashboard log file | `./dashboard.log` |
| `REPO_PATH` | Path to git repository for commit tracking | `/home/user/project` |
| `R2_ENDPOINT` | URL for uploading the JSON blob | `https://r2-proxy.millrace.ai/state.json` |
| `RUN_ID` | Static identifier for this run | `compiler-run-001` |
| `SYNC_INTERVAL` | Seconds between sync cycles (default: 60) | `60` |

---

## Runtime Behavior

### Startup Order

1. Start the log aggregator first. It creates `dashboard.log` (or appends to it if it exists).
2. Start the state-sync script. It tails `dashboard.log`.
3. Both run as background processes alongside the Millrace loops.

### Log Aggregator Main Loop
```
every CHECK_INTERVAL seconds (default: 1s):
  1. Read new lines from research.log since last offset
  2. Read new lines from orchestrate.log since last offset
  3. For each new line from either source:
     a. Apply sanitization rules (keep/strip)
     b. If kept: format timestamp, add source tag, normalize agent names
     c. Truncate to 120 chars
     d. Append to dashboard.log
  4. Interleave lines chronologically by timestamp
```

### State-Sync Main Loop
```
every SYNC_INTERVAL seconds (default: 60s):
  1. Read new lines from dashboard.log since last offset
  2. Parse each new line, update in-memory state
  3. Run git log to get latest commit
  4. Compute elapsed_seconds from first-event timestamp
  5. Serialize state to JSON
  6. POST to R2 endpoint
  7. Log one-line local status: "Synced: task 3/18, agent=builder, elapsed=4h12m"
```

### Log File Handling (Both Scripts)
- Use file read offsets to avoid re-reading entire files each cycle.
- If a file is truncated or rotated (size decreases), reset its read offset to 0 and re-parse.
- If a file doesn't exist yet at startup, wait and poll for its creation.

### Crash Recovery
- If the aggregator crashes and restarts, it re-reads both raw logs from the beginning and regenerates `dashboard.log`. Duplicate lines are acceptable — the state-sync script's state parser is idempotent on repeated events.
- If the state-sync script crashes and restarts, it re-parses `dashboard.log` from the beginning to reconstruct state.
- During any crash, the dashboard freezes on the last uploaded blob. The frozen timestamp IS the crash evidence. First successful upload after restart unfreezes it.

### Graceful Shutdown
- On SIGINT/SIGTERM, both scripts do a final cycle, then exit.
- They can be managed together via a simple wrapper script or process manager.

---

## Language and Dependencies

**Both scripts: Python 3, standard library only.**

- `json` for serialization
- `subprocess` for git commands
- `urllib.request` for HTTP uploads (or shell out to `curl`)
- `time` for main loops
- `os` / `pathlib` for file handling
- `re` for log line parsing

**Explicitly NOT used:**
- No frameworks (Flask, FastAPI, etc.)
- No WebSocket libraries
- No async/event-loop libraries
- No pip packages beyond standard library

---

## Important Caveats

### Log Format Is Not Yet Finalized
The exact format of Millrace's raw log output from `research_loop.sh` and `orchestrate_loop.sh` will determine the aggregator's parsing patterns. The aggregator will need a tuning pass after seeing real log output from a test run. Build the structure first, refine the regexes against actual data.

### Token Logging Comes From the Loop Scripts
Both `research_loop.sh` and `orchestrate_loop.sh` will emit token usage lines in their respective logs. The aggregator passes these through (sanitized), and the state-sync script accumulates them into running totals. The exact format of the token lines depends on what the loop scripts emit — coordinate with the loop script implementation to agree on a parseable format (e.g., `Tokens: in=245000 out=62000` or similar).

### These Scripts Must Not Interfere with the Build
- No file locking on any log file (read-only, tail-style)
- No heavy CPU or memory usage
- No network calls that could block or hang (use timeouts on all HTTP requests)
- If anything goes wrong, fail silently and try again next cycle
- The aggregator writes to its own output file — it never modifies the raw loop logs

### Test Data
For development, create mock log files that simulate a run:

```bash
# Terminal 1: simulate orchestration events
echo '[2026-03-20 14:28:37] Stage _start.md: starting — runner=codex model=gpt-5.2' >> mock_orchestrate.log
sleep 2
echo '[2026-03-20 14:35:12] _start.md: exit=0 status=### BUILDER_COMPLETE' >> mock_orchestrate.log
echo '[2026-03-20 14:35:12] Tokens: in=245000 out=62000' >> mock_orchestrate.log
sleep 2
echo '[2026-03-20 14:35:15] Stage _check.md: starting — runner=codex model=gpt-5.2' >> mock_orchestrate.log

# Terminal 2: simulate research events (for escalation testing)
echo '[2026-03-20 15:10:00] Stage _spec_synthesis.md: starting — mode=goalspec' >> mock_research.log
sleep 2
echo '[2026-03-20 15:15:30] _spec_synthesis.md: complete' >> mock_research.log
```

Run the aggregator against the mock files, then run the state-sync against the resulting `dashboard.log`. Verify the JSON blob is correct at each step.

---

## Deliverables

| File | Purpose | Estimated Size |
|------|---------|----------------|
| `log_aggregator.py` | Tails raw logs, sanitizes, writes combined dashboard log | ~80-120 lines |
| `state_sync.py` | Tails dashboard log, parses state, uploads JSON to R2 | ~150-200 lines |

Total: two Python files, no dependencies, ~250-320 lines combined.
