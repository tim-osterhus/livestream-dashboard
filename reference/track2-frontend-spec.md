# Mission Control Dashboard — Frontend Spec

## What This Is

A static React + TypeScript web app deployed to Cloudflare Pages at `live.millrace.ai`. It polls a JSON blob from Cloudflare R2 every 60 seconds and renders a livestream-optimized dashboard showing the real-time state of an autonomous software build.

The dashboard is an evidence artifact for a livestream, not an interactive application. There are no user controls, no buttons, no inputs. It is a display. A separate device (MacBook running OBS) opens this page fullscreen and streams it to YouTube/Twitch.

---

## Data Source

The app fetches a single JSON blob from an R2 endpoint every 60 seconds. The blob is ~2-5KB. There are no WebSockets, no SSE, no real-time connections.

### JSON Schema

```json
{
  "timestamp": "2026-XX-XXTXX:XX:XXZ",
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
    "agent_started_at": "2026-XX-XXTXX:XX:XXZ"
  },

  "tasks": [
    {
      "id": 1,
      "name": "Implement lexer and tokenizer",
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
    "timestamp": "2026-XX-XXTXX:XX:XXZ"
  },

  "log_lines": [
    "[14:28:37] Stage Builder: running (360s elapsed)",
    "[14:35:12] Builder: complete",
    "[14:35:12] Stage QA: starting — model=gpt-5.2",
    "[14:42:58] QA: result=QUICKFIX_NEEDED",
    "[14:43:01] Stage Hotfix: starting",
    "[14:50:22] Hotfix: complete",
    "[14:50:22] Progress: 2/18 tasks — elapsed 04h12m",
    "[14:50:25] Stage Builder: starting — task=\"Implement AST generation\""
  ]
}
```

### Key Schema Fields

- `loop.active_loop`: `"orchestration"` or `"research"` — drives which workshop scene is shown.
- `loop.research_mode`: `null` when orchestration is active, or `"goalspec"` / `"incident"` / `"audit"` when research is active — drives which set of workers appears in the research workshop.
- `pipeline.current_agent`: Maps to a specific worker sprite. Values for orchestration: `"start"`, `"integrate"`, `"check"`, `"hotfix"`, `"doublecheck"`, `"consult"`, `"troubleshoot"`, `"update"`. Values for research vary by mode (see Worker Ensembles below).
- Cost is NOT in the schema. It is hardcoded on the frontend to `$200`.

---

## Layout

Three zones plus a floating task bar. Primary target: 1920×1080 fullscreen.

```
┌──────────────────────────────────────────────┬──────────────┐
│                                              │              │
│                                              │   ZONE 2     │
│              ZONE 1                          │   Metrics    │
│              Workshop Scene                  │   Sidebar    │
│              (~80% width, ~80% height)       │   (~210px)   │
│                                              │              │
│           ┌──────────────────────┐           │              │
│           │   TASK BAR (float)   │           │              │
│           └──────────────────────┘           │              │
├──────────────────────────────────────────────┴──────────────┤
│                         ZONE 3                               │
│                         Log Ticker (~120px height)           │
└──────────────────────────────────────────────────────────────┘
```

---

## Zone 1: Workshop Scene

### Concept

An animated pixel-art workshop. Workers stand in a horseshoe/semicircle around a central workstation. One worker is active at a time — the rest idle. The entire scene swaps between two environments depending on which loop is running.

### Two Environments

Only the active loop's workshop is visible. The other is `opacity: 0`.

**Orchestration ("The Forge")**
- Central prop: anvil with spark particles (2-3 CSS-animated 2px divs drifting upward, only when a worker is active)
- Background feel: dark base (#222B31) with subtle warm undertone
- Shown when: `loop.active_loop === "orchestration"`

**Research ("The Study")**
- Central prop: table with books/scrolls
- Background feel: dark base (#222B31) with subtle cool undertone
- Shown when: `loop.active_loop === "research"`

### Scene Transition

When `active_loop` changes between polls, crossfade the two environments. Both exist in the DOM. CSS opacity transition, ~1 second duration.

### Horseshoe Layout

Workers are positioned in a semicircle, open end at bottom. The workstation prop sits at the center. Workers are evenly spaced along the arc with enough room to read each sprite and its name label.

The active worker is positioned slightly closer to the workstation center via a CSS `transform: translate()` transition (~0.5s ease). When the active worker changes, the previous one transitions back to its arc position and the new one transitions forward.

For positioning, calculate N evenly-spaced points along a semicircular arc (π to 0, i.e. left-to-right across the top). The arc should have generous radius — workers should not be cramped.

### Worker Ensembles

Each ensemble is a fixed set of workers that appears on screen when its loop/mode is active.

#### Orchestration (8 workers, always the same set)

| `current_agent` value | Display Name | Placeholder Color |
|----------------------|--------------|-------------------|
| `start` | Builder | #6B3D3D |
| `integrate` | Integrator | #3D5A6B |
| `check` | QA | #5A5A3D |
| `hotfix` | Hotfix | #4A6B3D |
| `doublecheck` | Doublecheck | #3D4A5A |
| `consult` | Consult | #6B3D5A |
| `troubleshoot` | Troubleshoot | #5A3D4A |
| `update` | Update | #6B5A4A |

#### Research — GoalSpec (9 workers, shown when `research_mode === "goalspec"`)

| `current_agent` value | Display Name |
|----------------------|--------------|
| `goal_intake` | Goal Intake |
| `spec_synthesis` | Spec Synthesis |
| `spec_review` | Spec Review |
| `critic` | Critic |
| `designer` | Designer |
| `taskmaster` | Taskmaster |
| `taskaudit` | Task Audit |
| `objective_profile_sync` | Objective Sync |
| `mechanic` | Mechanic |

#### Research — Incident (6 workers, shown when `research_mode === "incident"`)

| `current_agent` value | Display Name |
|----------------------|--------------|
| `incident_intake` | Incident Intake |
| `incident_resolve` | Incident Resolve |
| `incident_archive` | Incident Archive |
| `taskmaster` | Taskmaster |
| `taskaudit` | Task Audit |
| `mechanic` | Mechanic |

#### Research — Audit (6 workers, shown when `research_mode === "audit"`)

| `current_agent` value | Display Name |
|----------------------|--------------|
| `contractor` | Contractor |
| `audit_intake` | Audit Intake |
| `audit_validate` | Audit Validate |
| `audit_gatekeeper` | Audit Gatekeeper |
| `objective_profile_sync` | Objective Sync |
| `mechanic` | Mechanic |

### Worker States

| State | Visual |
|-------|--------|
| **Idle** | Static first frame of sprite sheet, ~20% opacity |
| **Active** | Full opacity, looping sprite animation, positioned closer to workstation |
| **Completion** | Brief transition animation (2-3 frames), then back to idle |

### Worker Name Labels

8px monospaced text, uppercase, centered below each worker sprite. Active worker's label: #C7080C. Idle workers' labels: #55666E.

### Sprite Rendering

Each worker has a horizontal PNG sprite strip. Animation uses CSS `background-image` + `background-position` shifted by `animation: steps()`.

```css
.worker-sprite {
  width: 32px;
  height: 32px;
  background-image: url('/sprites/builder.png');
  background-size: auto 32px;
  background-position: 0 0; /* idle: first frame */
}
.worker-sprite.active {
  animation: work 0.8s steps(6) infinite;
}
@keyframes work {
  from { background-position: 0 0; }
  to { background-position: -192px 0; } /* 6 frames × 32px */
}
```

**Placeholder sprites:** Until real sprite PNGs are available, render each worker as a colored rectangle (using the placeholder colors in the orchestration table above, or generated hues for research workers) with their name label below. The sprite integration is a drop-in replacement: swap `background-color` for `background-image`.

### Workstation Ambient Effects

Orchestration only: 2-3 spark particles. Each is a 2px div with a CSS keyframe that translates upward 15-20px while fading opacity to 0, looping on different durations (0.7s, 0.8s, 0.9s) with staggered delays. Only visible when any orchestration worker is active.

Research: no particles. The workstation prop sprite handles its own visual (subtle page-turn or candle implied through sprite frames).

---

## Task Bar

Floating at the bottom of Zone 1, above the log ticker. Horizontally centered within Zone 1's width.

### Content (left to right)

1. **Task counter**: `3 / 18` — `pipeline.current_task_index` / `pipeline.total_tasks`
2. **Task name**: Name of the task with `status === "active"` from the tasks array, truncated with ellipsis
3. **Mini pipeline**: 8 small rectangles representing stage progression for the current task

### Mini Pipeline Stages

The 8 stages in order: Research, Decompose, Builder, Integrate, QA, Hotfix, Doublecheck, Finalize.

The pipeline state is inferred: stages up to (but not including) the current agent are "done." The current agent's stage is "active." Everything after is "pending."

| State | Color |
|-------|-------|
| Done | #440101 |
| Active | #C7080C with `box-shadow: 0 0 6px #E2222744` |
| Pending | #55666E22 with 1px border #55666E22 |

Each rectangle: 20px wide, 6px tall, 1px border-radius, 3px gap between them.

### Styling

- Background: #2A353D
- Border: 1px solid #55666E33
- Padding: 10px 16px
- Task name: 13px monospaced, font-weight 500
- Counter: 10px monospaced, #888

---

## Zone 2: Metrics Sidebar

Fixed 210px wide column on the right. Background: #2A353D. Left border: 1px solid #55666E44. Padding: 16px 14px. All text monospaced (JetBrains Mono or Fira Code via Google Fonts CDN).

Metric groups are stacked vertically with 14-20px spacing. Each group has a label (9px uppercase, letter-spacing 1.8px, #55666E) above its value.

### Metrics (top to bottom)

**Cost Display**
- Value: `$200` — hardcoded, not from JSON
- Font: 32px bold
- Color: heat ramp based on overall progress (starts dim, warms toward #C7080C as tasks complete)

**Elapsed Time**
- Value: format `elapsed_seconds` as `Xh Xm`
- Font: 15px
- Color: #D0D0D0

**Active Agent**
- Value: display name of `pipeline.current_agent`
- Font: 15px, font-weight 500
- Color: #E22227
- Sub-line: `metrics.current_model` + " · cycle " + `metrics.cycle_number` in 10px #888

**Progress**
- Thin progress bar: 4px tall, full sidebar width, #55666E22 track, #440101 fill with `box-shadow: 1px 0 4px #C7080C44` on leading edge
- Fill width: (completed tasks / total tasks) × 100%
- Sub-line: "X done · 1 active · Y pending" in 10px #888

**Tokens**
- Single line: "IN XX.XM  OUT XX.XM"
- Format: divide raw numbers by 1,000,000, show 1 decimal
- Font: 10px #888

**Latest Commit**
- Hash: first 7 chars of `latest_commit.hash` in 11px #888
- Message: `latest_commit.message` truncated, in 10px #55666E
- On change: brief brightness flash (CSS transition on color, 0.3s), then settle back

**Test Results**
- One row per suite: name on left, "X pass  Y fail  / Z" on right
- Pass count color: #8B6914 (warm amber)
- Fail count color: #440101
- Total: 10px #888
- Initially hidden or shows "Awaiting activation" in dim #55666E for suites where `active === false` and all counts are 0
- Show suites only when they have data or `active === true`

---

## Zone 3: Log Ticker

Full width across the bottom. Height: ~120px. Background: #222B31. Top border: 1px solid #55666E44.

### Content

Renders `log_lines` from the JSON blob as a scrolling monospaced feed.

### Behavior

- Show the last 7-8 lines
- On each poll, if new lines exist (compare against previous state), append them and smooth-scroll to bottom
- Most recent 2 lines are slightly brighter (#888), older lines are dimmer (#55666E)

### Styling

- Font: 11px monospaced
- Line height: 1.8
- Padding: 8px 18px
- Lines truncated with ellipsis at container width
- Timestamps (the `[HH:MM:SS]` prefix) rendered in slightly dimmer color (#55666E66)

---

## Polling Logic

### Core Loop

```
every 60 seconds:
  fetch JSON blob from R2 endpoint
  if fetch fails: do nothing, retry next cycle
  if blob unchanged (same timestamp): update "last updated Xs ago" indicator
  if blob changed:
    diff against previous state
    trigger transitions for any changed fields
    store as new previous state
```

### State Diffing and Transitions

| Field Changed | Action |
|---------------|--------|
| `loop.active_loop` | Crossfade workshop scenes (1s opacity transition) |
| `loop.research_mode` | Swap research worker ensemble (0.5s fade) |
| `pipeline.current_agent` | Transition active worker: old → idle, new → active (0.5s) |
| `pipeline.current_task_index` or `total_tasks` | Update task bar counter and name |
| `metrics.*` | Update sidebar values |
| `tests.*` | Update test result displays; if suite transitions from all-zero to having data, reveal with a brief fade-in |
| `latest_commit.hash` | Flash commit display, update values |
| `log_lines` | Append new lines to ticker, smooth-scroll |

### Stale Data Indicator

If the blob's `timestamp` hasn't changed for 2+ consecutive polls (120+ seconds), show a small "Last updated Xs ago" text in dim gray somewhere unobtrusive (bottom of sidebar or corner of workshop scene). This surfaces build machine crashes without alarming non-technical viewers.

---

## Idle State (Pre-Run)

The dashboard must look good from the moment it launches, before any data arrives:

- Orchestration workshop visible, all workers at 20% opacity, no animations
- Workstation dark (no sparks)
- Task bar: `0 / 0`, empty name, all mini pipeline stages pending
- Sidebar: all metrics show `--` or `0` in dim gray (#55666E)
- Test results: all show "Awaiting activation"
- Log ticker: single line `[--:--:--] Awaiting orchestration start...`
- Cost display still shows `$200` (it's always there)

---

## Color Reference

| Token | Hex | Usage |
|-------|-----|-------|
| Background | #222B31 | Main background |
| Surface | #2A353D | Sidebar, task bar |
| Muted | #55666E | Labels, borders, idle text, log lines |
| Text Primary | #D0D0D0 | Readable text, elapsed time |
| Text Secondary | #888888 | Metrics sub-lines, recent log lines |
| Heat Ember | #440101 | Done indicators, progress fill |
| Heat Hot | #C7080C | Active worker labels, active stage glow |
| Heat Blazing | #E22227 | Active agent text, workshop title |
| Amber | #8B6914 | Test pass counts |

---

## Typography

All text uses JetBrains Mono or Fira Code (import from Google Fonts CDN).

| Element | Size | Weight |
|---------|------|--------|
| Cost display | 32px | 700 |
| Metric values | 15px | 500 |
| Metric labels | 9px uppercase, letter-spacing 1.8px | 400 |
| Task bar name | 13px | 500 |
| Task bar counter | 10px | 400 |
| Worker name labels | 8px uppercase | 400 (700 when active) |
| Log lines | 11px | 400 |
| Log timestamps | 11px | 400 |

---

## Responsive Fallbacks (Low Priority)

Primary target is 1920×1080 fullscreen. These are secondary:

- Below 1200px: sidebar stacks below workshop
- Below 768px: show only active worker (no horseshoe), metrics below, log ticker collapses to single status line

Do not let responsive concerns compromise the 1080p layout.

---

## Deployment

- Cloudflare Pages
- Static build (no server-side rendering needed)
- R2 endpoint URL for JSON blob polling should be configurable (environment variable or config file)
- No authentication on the dashboard — it's publicly accessible
- Domain: `live.millrace.ai`

---

## Performance Constraints

This page will be open fullscreen on a 2017 MacBook Pro that is simultaneously running OBS to stream to YouTube/Twitch. Performance is critical.

- **CSS animations only.** No canvas, no WebGL, no requestAnimationFrame rendering loops.
- **No JavaScript-driven animation.** All sprite animation, transitions, and effects use CSS `animation`, `transition`, and `opacity`.
- **Sprite sheets are static PNGs**, preloaded on page init.
- **One fetch every 60 seconds.** No polling faster, no retry storms.
- **Target: zero dropped frames on OBS.**

---

## Watermark

Small text in the bottom-right corner of the workshop scene: "Sprite art generated by Millrace" — 7px, color #55666E22 (barely visible, discoverable on close inspection).
