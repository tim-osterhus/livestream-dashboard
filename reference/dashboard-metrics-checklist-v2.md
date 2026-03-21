# Dashboard Data Requirements Checklist v2

This is a reality-checked companion to `_livestream_dashboard/dashboard-metrics-checklist.md`.

It maps each checklist row to the current Millrace runtime behavior in:

- `baseline-framework/millrace/agents/orchestrate_loop.sh`
- `baseline-framework/millrace/agents/research_loop.sh`
- adjacent runtime artifacts that those loops write during operation

## Scoring Method

- `Logged`: the loop already emits a usable runtime signal during operation.
- `Partial`: the data exists, but only in a side artifact, only for some runners, or in a format that does not cleanly match the checklist's expected dashboard parser contract.
- `Gap/External`: the loops do not currently emit the metric in a usable runtime form, or the item depends on launcher/config/repo state rather than loop logging.

## Summary

- Strictly usable runtime logging today: `12 / 29`
- Partial or artifact-backed signals: `7 / 29`
- Missing or external/setup-dependent: `10 / 29`

Notes:

- The original checklist contains some duplicated verification rows near the end (`Research mode emission`, `Token counts`, `Task names in orchestration log`, `Test suite output format`, `Escalation handoff logging`). They are still scored here because they are present as checklist rows.
- The recent Codex token work means both loops now emit a shared `Token usage:` format for Codex invocations, but not for Claude/OpenClaw runs.

## Row-By-Row Audit

| # | Checklist Item | Status | Current Source | Current Reality / Gap |
|---|---|---|---|---|
| 1 | Active loop indicator | Gap/External | `commands.md:80-81`, `commands.md:129-130` | The example launch paths start each loop in tmux but do not redirect them to dedicated `research.log` / `orchestrate.log` files. The aggregator can still distinguish loops if the operator tails separate outputs, but the loop scripts do not guarantee dedicated log files by themselves. |
| 2 | Research mode | Partial | `baseline-framework/millrace/agents/research_loop.sh:10183`, `baseline-framework/millrace/agents/research_loop.sh:10230`, `baseline-framework/millrace/agents/research_loop.sh:10694` | Actual mode dispatch is persisted as `MODE_DISPATCH mode=...` in `agents/research_events.md`, and startup config logs `research_mode=...`, but there is no explicit runtime line like `Research mode: goalspec` on every switch. |
| 3 | Agent start event | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:1308`, `baseline-framework/millrace/agents/research_loop.sh:6568`, `baseline-framework/millrace/agents/research_loop.sh:7633` | Both loops emit a stage-start line before each agent invocation. The wording is `runner=... model=...` rather than `starting`, but it is a reliable start signal. |
| 4 | Agent completion event | Partial | `baseline-framework/millrace/agents/orchestrate_loop.sh:1361`, `baseline-framework/millrace/agents/orchestrate_loop.sh:5330`, `baseline-framework/millrace/agents/research_loop.sh:6621` | Completion is logged, but not uniformly in the checklist's preferred `AGENT_ID: exit=CODE status=STATUS` format. Research logs `exit=0`, but not a stage status marker on the same line. |
| 5 | Agent identifier consistency | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:1308`, `baseline-framework/millrace/agents/research_loop.sh:7633` | Orchestration uses stable display-stage labels like `Builder`, `QA`, `Consult`; research uses stable `Research-$stage` labels. |
| 6 | Current model name | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:1308`, `baseline-framework/millrace/agents/research_loop.sh:6568` | Both loops include `model=...` on stage-start lines. |
| 7 | Current task index and total | Gap/External | `baseline-framework/millrace/agents/orchestrate_loop.sh:2996`, `baseline-framework/millrace/agents/orchestrate_loop.sh:4987` | Orchestration logs `tasks_completed` and `tasks_demoted`, but never logs a `current/total` pair like `3/18 tasks`. |
| 8 | Task name | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:5068`, `baseline-framework/millrace/agents/orchestrate_loop.sh:4987`, `baseline-framework/millrace/agents/orchestrate_loop.sh:742` | The orchestration loop logs `Task: <heading>` when a card starts, and logs the completed task name again in the completion progress line. |
| 9 | Task completion event | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:4977-4987` | `Finalize:` plus `Progress: tasks_completed=... task="..."` gives a deterministic completion signal at task closeout. |
| 10 | Per-stage token counts | Partial | `baseline-framework/millrace/agents/orchestrate_loop.sh:1561-1632`, `baseline-framework/millrace/agents/research_loop.sh:582-649` | Both loops now emit per-invocation `Token usage:` lines, but only for Codex runs. Claude and OpenClaw do not yet emit equivalent loop-level token lines. |
| 11 | Consistent token format | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:1580-1628`, `baseline-framework/millrace/agents/research_loop.sh:595-643` | The two loops now use the same `Token usage: stage=... runner=codex model=... input=... cached=... output=... stdout=...` format. |
| 12 | Input and output separated | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:1613-1615`, `baseline-framework/millrace/agents/research_loop.sh:628-630` | Token lines carry separate `input=` and `output=` values, plus `cached=`. |
| 13 | Cycle increment signal | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:4985-4987`, `baseline-framework/millrace/agents/orchestrate_loop.sh:2994-2996` | The loop increments `tasks_completed` on success and `tasks_demoted` on blocked/demoted cards. This is enough to derive a cycle counter, even though the format differs from `Progress: CURRENT/TOTAL tasks`. |
| 14 | Timestamps on all log lines | Partial | `baseline-framework/millrace/agents/orchestrate_loop.sh:246`, `baseline-framework/millrace/agents/research_loop.sh:244` | The main `log()` path timestamps lines with second precision, but not every emitted line goes through `log()`. Direct `echo`/tool output still exists. |
| 15 | First event timestamp | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:246`, `baseline-framework/millrace/agents/research_loop.sh:244` | The first real runtime events are normally emitted through `log()`, so the dashboard can anchor elapsed time from the first timestamped stage event. |
| 16 | Agent start timestamp precision | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:246`, `baseline-framework/millrace/agents/research_loop.sh:244` | The loop timestamp format includes seconds. |
| 17 | Git commits happening | Gap/External | `baseline-framework/millrace/agents/orchestrate_loop.sh:4783`, `baseline-framework/millrace/agents/orchestrate_loop.sh:4750-4767` | Commit/publish behavior exists in the orchestrator's post-QA staging pipeline, but the dashboard field comes from `git log -1`, not loop log lines. This is repo-state behavior, not a runtime log metric. |
| 18 | Repo path accessible | Gap/External | N/A | This is deployment/config only. It is not emitted by the loops. |
| 19 | Test suite execution output | Gap/External | `baseline-project/harness/run_c_compiler_harness.sh:177`, `baseline-project/harness/run_c_compiler_harness.sh:320-323`, `baseline-project/harness/run_c_compiler_harness.sh:558`, `baseline-project/harness/run_c_compiler_harness.sh:605`, `baseline-project/harness/run_c_compiler_harness.sh:650`, `baseline-project/harness/run_c_compiler_harness.sh:795-797` | The compiler harness writes structured results to summary artifacts and per-suite logs, but `orchestrate_loop.sh` does not mirror those results into dashboard-friendly loop log lines like `Test gcc_torture: passed=... failed=... total=...`. |
| 20 | Per-suite results | Gap/External | same harness sources as row 19 | Per-suite data exists in harness result files, but not in orchestration runtime logs. |
| 21 | Test activation signal | Gap/External | N/A in loop logs | There is no runtime line that cleanly marks "test panel active now". |
| 22 | QA verdicts | Partial | `baseline-framework/millrace/agents/orchestrate_loop.sh:5330`, `baseline-framework/millrace/agents/orchestrate_loop.sh:5367`, `baseline-framework/millrace/agents/orchestrate_loop.sh:5395` | QA logs include `status=### QA_COMPLETE` / `### QUICKFIX_NEEDED`, which is close to the dashboard need, but there is no single standardized `QA: result=...` runtime line across all verdict paths. |
| 23 | Escalation events | Partial | `baseline-framework/millrace/agents/orchestrate_loop.sh:2961-2982`, `baseline-framework/millrace/agents/orchestrate_loop.sh:4008-4049` | Rich escalation notes exist in `runner_notes.md`, and stderr logs show blocker escalation flow (`Blocker: running Consult`, etc.), but there is no single canonical runtime handoff line tailored for the dashboard. |
| 24 | Blocker events | Logged | `baseline-framework/millrace/agents/orchestrate_loop.sh:4008-4021`, `baseline-framework/millrace/agents/orchestrate_loop.sh:4915-4918` | The orchestrator emits explicit blocker lines with stage, reason, diagnostics, and failure signature. |
| 25 | Research mode emission | Partial | same sources as row 2 | Same underlying condition as row 2: mode is persisted, but not emitted as a clean `Research mode: X` runtime line. |
| 26 | Token counts | Partial | same sources as row 10 | Same underlying condition as row 10: token logging exists for Codex, not for every supported runner. |
| 27 | Task names in orchestration log | Logged | same sources as row 8 | Same underlying condition as row 8: task names are already logged at task start and completion. |
| 28 | Test suite output format | Gap/External | same harness sources as row 19 | Structured test outputs exist in harness artifacts, but the loop logs do not currently expose a dashboard parser format. |
| 29 | Escalation handoff logging | Partial | same sources as row 23 | Same underlying condition as row 23: there are escalation artifacts and runner notes, but no single loop-log handoff line designed for dashboard scene switching. |

## What Is Already Good Enough For a Dashboard Parser

These are the strongest existing signals:

- Timestamped stage-start lines in both loops
- Stable stage/agent identifiers
- Model names on stage-start lines
- Task names in orchestration
- Task completion via `tasks_completed` progress increments
- Blocker lines in orchestration
- Codex token lines in a shared format across both loops

## Biggest Current Gaps

These are the largest blockers to the checklist as written:

1. No default dedicated `research.log` / `orchestrate.log` emission contract
2. No explicit `Research mode: X` runtime line on each dispatch/switch
3. No `current/total` task progress denominator
4. No dashboard-ready test-suite result lines in the orchestration log
5. No single canonical escalation handoff line in the loop stderr/stdout stream

## Practical Bottom Line

If the dashboard only consumes live loop logs, Millrace is not fully there yet.

If the dashboard is allowed to combine:

- loop stderr/stdout
- `runner_notes.md`
- `agents/research_events.md`
- harness summary artifacts like `summary.tsv` / `summary.json`

then a larger share of the checklist becomes inferable, but the parser becomes much more bespoke and fragile than the original checklist intends.
