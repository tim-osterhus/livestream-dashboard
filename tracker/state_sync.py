#!/usr/bin/env python3
"""Millrace livestream tracker: dashboard-log -> state blob uploader.

Best-guess implementation of track3-state-sync-spec-v2.md.

Important ambiguities handled here:
- dashboard.log only contains HH:MM:SS, but the JSON schema wants full ISO
  timestamps. This script reconstructs dates using a configurable tracker
  timezone plus midnight-rollover detection. Default: UTC.
- pipeline.current_agent is inconsistent inside the spec: the example JSON uses
  friendly values like "builder", while the field-derivation table says blob
  values like "start". This script defaults to the table's blob values and lets
  you switch to friendly values with AGENT_VALUE_STYLE=friendly.
- Token lines may be per-stage deltas or cumulative totals. This script treats
  lines containing words like "cumulative", "running total", "overall", or
  "lifetime" as absolute totals; everything else is treated as a delta.
- Duplicate dashboard lines are ignored for state transitions using an exact-line
  fingerprint. That is the simplest way to make crash-restart replay idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ should have zoneinfo
    ZoneInfo = None  # type: ignore

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # pragma: no cover - watchdog is optional
    FileSystemEventHandler = None  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]

SYNC_INTERVAL_DEFAULT = 60.0
RETRY_DELAY_DEFAULT = 5.0
HTTP_TIMEOUT_DEFAULT = 10.0
EVENT_DEBOUNCE_DEFAULT = 1.0
EVENT_HEARTBEAT_DEFAULT = 600.0
EVENT_CHECK_DEFAULT = 5.0
DEFAULT_TEST_SUITES = ["runtime", "queue", "closure", "site"]
DEFAULT_AGENT_VALUE_STYLE = "blob"
DEFAULT_LOG_TAIL = 10
EM_DASH = " — "

DISPLAY_AGENT_TO_BLOB = {
    "Builder": "start",
    "Integrator": "integrate",
    "QA": "check",
    "Hotfix": "hotfix",
    "Doublecheck": "doublecheck",
    "Consult": "consult",
    "Troubleshoot": "troubleshoot",
    "Update": "update",
    "Goal Intake": "goal_intake",
    "Spec Synthesis": "spec_synthesis",
    "Spec Review": "spec_review",
    "Critic": "critic",
    "Designer": "designer",
    "Taskmaster": "taskmaster",
    "Task Audit": "taskaudit",
    "Objective Sync": "objective_profile_sync",
    "Mechanic": "mechanic",
    "Incident Intake": "incident_intake",
    "Incident Resolve": "incident_resolve",
    "Incident Archive": "incident_archive",
    "Contractor": "contractor",
    "Audit Intake": "audit_intake",
    "Audit Validate": "audit_validate",
    "Audit Gatekeeper": "audit_gatekeeper",
}

DISPLAY_AGENT_TO_FRIENDLY = {
    "Builder": "builder",
    "Integrator": "integrator",
    "QA": "qa",
    "Hotfix": "hotfix",
    "Doublecheck": "doublecheck",
    "Consult": "consult",
    "Troubleshoot": "troubleshoot",
    "Update": "update",
    "Goal Intake": "goal_intake",
    "Spec Synthesis": "spec_synthesis",
    "Spec Review": "spec_review",
    "Critic": "critic",
    "Designer": "designer",
    "Taskmaster": "taskmaster",
    "Task Audit": "task_audit",
    "Objective Sync": "objective_sync",
    "Mechanic": "mechanic",
    "Incident Intake": "incident_intake",
    "Incident Resolve": "incident_resolve",
    "Incident Archive": "incident_archive",
    "Contractor": "contractor",
    "Audit Intake": "audit_intake",
    "Audit Validate": "audit_validate",
    "Audit Gatekeeper": "audit_gatekeeper",
}

RESEARCH_MODE_AGENT_MAP = {
    "Goal Intake": "goalspec",
    "Spec Synthesis": "goalspec",
    "Spec Review": "goalspec",
    "Critic": "goalspec",
    "Designer": "goalspec",
    "Objective Sync": "goalspec",
    "Incident Intake": "incident",
    "Incident Resolve": "incident",
    "Incident Archive": "incident",
    "Contractor": "audit",
    "Audit Intake": "audit",
    "Audit Validate": "audit",
    "Audit Gatekeeper": "audit",
}

MODE_META_RE = re.compile(r"\bmode=(goalspec|incident|audit)\b", re.IGNORECASE)
MODEL_RE = re.compile(r"\bmodel=([A-Za-z0-9._-]+)\b")
PROGRESS_RE = re.compile(r"\bProgress:\s*(\d+)\s*/\s*(\d+)\s+tasks?\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"\bTokens?:.*?\bin\s*=\s*(\d+)\b.*?\bout\s*=\s*(\d+)\b", re.IGNORECASE)
TOKEN_CACHED_RE = re.compile(r"\bcached\s*=\s*(\d+)\b", re.IGNORECASE)
TASK_QUOTED_RE = re.compile(r"\btask=(?:\"([^\"]+)\"|'([^']+)')")
TASK_UNQUOTED_RE = re.compile(r"\btask=([^—]+?)(?:$|\s+runner=|\s+model=|\s+mode=)", re.IGNORECASE)
STAGE_START_RE = re.compile(r"^Stage\s+(.+?):\s*starting\b(?:\s*[—-]\s*(.*))?$", re.IGNORECASE)
STAGE_EVENT_RE = re.compile(r"^(?:Stage\s+.+?:\s*(?:starting|running|complete)\b|.+?:\s*(?:complete|running|result=[A-Z_]+))", re.IGNORECASE)
TEST_STRUCTURED_RE = re.compile(
    r"^(?:Test|Suite)?\s*([A-Za-z0-9_.-]+):\s*passed=(\d+)\s+failed=(\d+)\s+total=(\d+)(?:\s+active=(true|false))?",
    re.IGNORECASE,
)
TEST_FREEFORM_RE = re.compile(
    r"\b([A-Za-z0-9_.-]+)\b.*?\bpassed=(\d+)\b.*?\bfailed=(\d+)\b.*?\btotal=(\d+)\b(?:.*?\bactive=(true|false)\b)?",
    re.IGNORECASE,
)
DASHBOARD_LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[(ORCH|RES)\]\s+(.*)$")

STOP_REQUESTED = False


def handle_signal(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


@dataclass
class TrackerConfig:
    dashboard_log: Path
    repo_path: Optional[Path]
    millrace_workspace: Optional[Path]
    r2_endpoint: Optional[str]
    output_json_path: Optional[Path]
    run_id: str
    sync_interval: float
    http_timeout: float
    retry_delay: float
    upload_method: str
    tracker_tz: str
    agent_value_style: str
    test_suites: List[str]
    log_tail_size: int
    event_driven: bool = False
    event_debounce_seconds: float = EVENT_DEBOUNCE_DEFAULT
    event_heartbeat_seconds: float = EVENT_HEARTBEAT_DEFAULT
    event_check_seconds: float = EVENT_CHECK_DEFAULT
    once: bool = False
    dry_run: bool = False
    stdout_json: bool = False


@dataclass
class ParserState:
    current_line_date: Optional[date] = None
    last_line_dt: Optional[datetime] = None
    first_event_at: Optional[datetime] = None
    active_loop: Optional[str] = None
    research_mode: Optional[str] = None
    current_agent_display: Optional[str] = None
    current_task_index: int = 0
    total_tasks: int = 0
    agent_started_at: Optional[datetime] = None
    completed_tasks_count: int = 0
    current_model: Optional[str] = None
    token_in_total: int = 0
    token_out_total: int = 0
    token_cached_total: int = 0
    known_task_names: Dict[int, str] = field(default_factory=dict)
    active_task_index: Optional[int] = None
    seen_line_fingerprints: Set[str] = field(default_factory=set)
    tests: Dict[str, Dict[str, object]] = field(default_factory=dict)
    log_lines: Deque[str] = field(default_factory=lambda: deque(maxlen=DEFAULT_LOG_TAIL))


class StateSync:
    def __init__(self, config: TrackerConfig) -> None:
        self.config = config
        self.offset = 0
        self.inode: Optional[int] = None
        self.partial = ""
        self.state = ParserState(log_lines=deque(maxlen=config.log_tail_size))
        self.tzinfo = self._load_tz(config.tracker_tz)
        self.anchor_date = self._initial_anchor_date(config.dashboard_log)
        self._init_tests()

    def run_forever(self) -> None:
        if self.config.once:
            self.process_cycle()
            return
        if self.config.event_driven:
            self._run_event_driven()
            return
        self._run_interval_loop()

    def _run_interval_loop(self) -> None:
        while True:
            self.process_cycle()
            if STOP_REQUESTED:
                break
            self._interruptible_sleep(self.config.sync_interval)

    def _run_event_driven(self) -> None:
        if Observer is None or FileSystemEventHandler is None:
            print("[state_sync] watchdog unavailable; falling back to interval sync", file=sys.stderr)
            self._run_interval_loop()
            return

        pending = threading.Event()
        syncer = self

        class Handler(FileSystemEventHandler):  # type: ignore[misc, valid-type]
            def on_any_event(self, event: object) -> None:
                src_path = getattr(event, "src_path", "")
                dest_path = getattr(event, "dest_path", "")
                paths = [Path(value) for value in (src_path, dest_path) if value]
                if any(syncer._is_relevant_event_path(path) for path in paths):
                    pending.set()

        observer = Observer()  # type: ignore[operator]
        handler = Handler()
        scheduled: Set[str] = set()
        for root, recursive in self._event_watch_specs():
            if not root.exists():
                continue
            watch_root = root if root.is_dir() else root.parent
            key = f"{watch_root.resolve()}:{recursive}"
            if key in scheduled:
                continue
            observer.schedule(handler, str(watch_root), recursive=recursive)
            scheduled.add(key)

        if not scheduled:
            print("[state_sync] no event watch paths exist; falling back to interval sync", file=sys.stderr)
            self._run_interval_loop()
            return

        self.process_cycle()
        last_fingerprint = self._event_fingerprint()
        last_heartbeat_at = time.time()
        print(
            (
                f"[state_sync] event-driven sync active; watching {len(scheduled)} roots; "
                f"heartbeat={self._format_duration(int(self.config.event_heartbeat_seconds))}; "
                f"check={self._format_duration(int(self.config.event_check_seconds))}"
            ),
            file=sys.stderr,
        )

        observer.start()
        try:
            while not STOP_REQUESTED:
                heartbeat = max(0.0, self.config.event_heartbeat_seconds)
                check_interval = max(0.1, self.config.event_check_seconds)
                if heartbeat > 0:
                    heartbeat_remaining = max(0.0, heartbeat - (time.time() - last_heartbeat_at))
                    timeout = min(check_interval, heartbeat_remaining or check_interval)
                else:
                    timeout = check_interval
                triggered = pending.wait(timeout)
                if STOP_REQUESTED:
                    break
                if triggered:
                    pending.clear()
                    self._wait_for_event_quiet(pending)
                    last_fingerprint = self._event_fingerprint()
                    self.process_cycle()
                    continue

                next_fingerprint = self._event_fingerprint()
                if next_fingerprint != last_fingerprint:
                    last_fingerprint = next_fingerprint
                    self.process_cycle()
                    continue

                heartbeat_due = heartbeat > 0 and (time.time() - last_heartbeat_at) >= heartbeat
                if heartbeat_due:
                    last_heartbeat_at = time.time()
                    self.process_cycle()
        finally:
            observer.stop()
            observer.join(timeout=5)

    def _wait_for_event_quiet(self, pending: threading.Event) -> None:
        debounce = max(0.0, self.config.event_debounce_seconds)
        if debounce <= 0:
            return
        deadline = time.time() + debounce
        while not STOP_REQUESTED:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            if pending.wait(remaining):
                pending.clear()
                deadline = time.time() + debounce

    def process_cycle(self) -> None:
        self._ingest_new_dashboard_lines()
        blob = self._build_state_blob()
        uploaded = self._upload_or_emit(blob)
        self._print_status(blob, uploaded=uploaded)

    def _ingest_new_dashboard_lines(self) -> None:
        path = self.config.dashboard_log
        if not path.exists():
            return

        stat = path.stat()
        inode = getattr(stat, "st_ino", None)
        truncated = stat.st_size < self.offset
        rotated = self.inode is not None and inode is not None and inode != self.inode
        if truncated or rotated:
            self._reset_parser_state(new_anchor_date=self._initial_anchor_date(path))

        self.inode = inode
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
            self.offset = handle.tell()

        if not chunk:
            return

        raw = self.partial + chunk
        lines, self.partial = self._split_complete_lines(raw)
        for line in lines:
            stripped = line.rstrip("\n")
            if stripped:
                self.state.log_lines.append(stripped)
            self._parse_dashboard_line(stripped)

    def _parse_dashboard_line(self, line: str) -> None:
        match = DASHBOARD_LINE_RE.match(line)
        if not match:
            return

        clock, source_tag, content = match.groups()
        event_dt = self._resolve_event_datetime(clock)
        if self.state.first_event_at is None and content.strip().lower() != "idle":
            self.state.first_event_at = event_dt

        fingerprint = f"{clock}|{source_tag}|{content}"
        if fingerprint in self.state.seen_line_fingerprints:
            return
        self.state.seen_line_fingerprints.add(fingerprint)

        source = "research" if source_tag == "RES" else "orchestration"

        if STAGE_EVENT_RE.match(content):
            self.state.active_loop = source
            if source == "orchestration":
                self.state.research_mode = None

        self._parse_stage_start(content, source=source, event_dt=event_dt)
        self._parse_progress(content)
        self._parse_tokens(content)
        self._parse_tests(content)
        self._parse_research_mode(content, source=source)

    def _parse_stage_start(self, content: str, source: str, event_dt: datetime) -> None:
        match = STAGE_START_RE.match(content)
        if not match:
            return

        agent_display = match.group(1).strip()
        meta = (match.group(2) or "").strip()
        self.state.current_agent_display = agent_display
        self.state.agent_started_at = event_dt

        model_match = MODEL_RE.search(meta)
        if model_match:
            self.state.current_model = model_match.group(1)

        if source == "research":
            self._parse_research_mode(content, source=source)

        task_name = self._extract_task_name(meta)
        short_agent = self._agent_value(agent_display)

        if source == "orchestration" and agent_display == "Builder":
            next_index = self._infer_next_task_index()
            self.state.current_task_index = next_index
            self.state.active_task_index = next_index
            if task_name:
                self.state.known_task_names[next_index] = task_name
        elif task_name:
            inferred_index = self._infer_next_task_index()
            self.state.known_task_names.setdefault(inferred_index, task_name)

    def _parse_progress(self, content: str) -> None:
        match = PROGRESS_RE.search(content)
        if not match:
            return
        completed, total = int(match.group(1)), int(match.group(2))
        self.state.completed_tasks_count = completed
        self.state.total_tasks = total
        if completed >= total:
            self.state.current_task_index = completed
            self.state.active_task_index = None
        elif self.state.active_task_index is None:
            self.state.current_task_index = completed

    def _parse_tokens(self, content: str) -> None:
        match = TOKEN_RE.search(content)
        if not match:
            return
        tokens_in, tokens_out = int(match.group(1)), int(match.group(2))
        cached_match = TOKEN_CACHED_RE.search(content)
        tokens_cached = int(cached_match.group(1)) if cached_match else 0
        lowered = content.lower()
        is_absolute = any(
            marker in lowered
            for marker in ("cumulative", "running total", "overall", "lifetime", "so far", "total_in", "total_out")
        )
        if is_absolute:
            self.state.token_in_total = tokens_in
            self.state.token_out_total = tokens_out
            self.state.token_cached_total = tokens_cached
        else:
            self.state.token_in_total += tokens_in
            self.state.token_out_total += tokens_out
            self.state.token_cached_total += tokens_cached

    def _parse_research_mode(self, content: str, source: str) -> None:
        if source != "research":
            return
        mode_match = MODE_META_RE.search(content)
        if mode_match:
            self.state.research_mode = mode_match.group(1).lower()
            return
        agent_match = STAGE_START_RE.match(content)
        if agent_match:
            agent_display = agent_match.group(1).strip()
        else:
            agent_display = content.split(":", 1)[0].strip() if ":" in content else ""
        mapped = RESEARCH_MODE_AGENT_MAP.get(agent_display)
        if mapped:
            self.state.research_mode = mapped

    def _parse_tests(self, content: str) -> None:
        structured = TEST_STRUCTURED_RE.search(content)
        match = structured or TEST_FREEFORM_RE.search(content)
        if not match:
            return
        suite_name = self._normalize_suite_name(match.group(1))
        passed = int(match.group(2))
        failed = int(match.group(3))
        total = int(match.group(4))
        active_raw = match.group(5)
        active = (active_raw.lower() == "true") if active_raw else total > 0
        if suite_name not in self.state.tests:
            self.state.tests[suite_name] = {"passed": 0, "failed": 0, "total": 0, "active": False}
        self.state.tests[suite_name] = {
            "passed": passed,
            "failed": failed,
            "total": total,
            "active": active,
        }

    def _build_state_blob(self) -> Dict[str, object]:
        now_utc = datetime.now(timezone.utc)
        current_task_index = self._effective_current_task_index()
        total_tasks = max(self.state.total_tasks, max(self.state.known_task_names.keys(), default=0))
        tasks = self._build_tasks_array(current_task_index=current_task_index, total_tasks=total_tasks)
        latest_commit = self._read_latest_commit()
        agent_started_at = self.state.agent_started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if self.state.agent_started_at else None
        elapsed_seconds = 0
        if self.state.first_event_at is not None:
            elapsed_seconds = max(0, int((now_utc - self.state.first_event_at.astimezone(timezone.utc)).total_seconds()))

        active_loop = self.state.active_loop
        research_mode = self.state.research_mode if active_loop == "research" else None
        current_agent = self._agent_value(self.state.current_agent_display) if self.state.current_agent_display else None

        blob = {
            "timestamp": now_utc.isoformat().replace("+00:00", "Z"),
            "run_id": self.config.run_id,
            "elapsed_seconds": elapsed_seconds,
            "tracker": self._tracker_blob(),
            "loop": {
                "active_loop": active_loop,
                "research_mode": research_mode,
            },
            "pipeline": {
                "current_agent": current_agent,
                "current_task_index": current_task_index,
                "total_tasks": total_tasks,
                "agent_started_at": agent_started_at,
            },
            "tasks": tasks,
            "metrics": {
                "tokens_in": self.state.token_in_total,
                "tokens_out": self.state.token_out_total,
                "cached_tokens": self.state.token_cached_total,
                "current_model": self.state.current_model,
                "cycle_number": self.state.completed_tasks_count,
            },
            "tests": self.state.tests,
            "latest_commit": latest_commit,
            "log_lines": list(self.state.log_lines)[-self.config.log_tail_size :],
        }
        return blob

    def _tracker_blob(self) -> Dict[str, object]:
        return {
            "sync_mode": "event_driven" if self.config.event_driven else "interval",
            "heartbeat_seconds": int(self.config.event_heartbeat_seconds) if self.config.event_driven else None,
            "check_seconds": self.config.event_check_seconds if self.config.event_driven else None,
            "debounce_seconds": self.config.event_debounce_seconds if self.config.event_driven else None,
        }

    def _build_tasks_array(self, current_task_index: int, total_tasks: int) -> List[Dict[str, object]]:
        tasks: List[Dict[str, object]] = []
        has_active_task = (
            total_tasks > 0
            and self.state.completed_tasks_count < total_tasks
            and current_task_index > self.state.completed_tasks_count
        )
        active_agent = (
            self._agent_value(self.state.current_agent_display)
            if self.state.current_agent_display and self.state.active_loop == "orchestration"
            else None
        )

        for idx in range(1, total_tasks + 1):
            if idx in self.state.known_task_names:
                name = self.state.known_task_names[idx]
            elif idx > self.state.completed_tasks_count:
                name = f"Pending task {idx}"
            else:
                name = f"Task {idx}"

            if idx <= self.state.completed_tasks_count:
                status = "complete"
                task: Dict[str, object] = {"id": idx, "name": name, "status": status}
            elif has_active_task and idx == current_task_index:
                task = {"id": idx, "name": name, "status": "active"}
                if active_agent:
                    task["active_agent"] = active_agent
            else:
                task = {"id": idx, "name": name, "status": "pending"}
            tasks.append(task)
        return tasks

    def _effective_current_task_index(self) -> int:
        if self.state.active_task_index is not None:
            return self.state.active_task_index
        return self.state.current_task_index

    def _infer_next_task_index(self) -> int:
        total_hint = self.state.total_tasks or max(self.state.known_task_names.keys(), default=0)
        next_index = self.state.completed_tasks_count + 1
        if total_hint:
            return min(max(1, next_index), total_hint)
        return max(1, next_index)

    def _extract_task_name(self, meta: str) -> Optional[str]:
        if not meta:
            return None
        match = TASK_QUOTED_RE.search(meta)
        if match:
            return (match.group(1) or match.group(2) or "").strip() or None
        match = TASK_UNQUOTED_RE.search(meta)
        if match:
            return match.group(1).strip().rstrip(" ,") or None
        return None

    def _agent_value(self, display_name: Optional[str]) -> Optional[str]:
        if not display_name:
            return None
        if self.config.agent_value_style == "friendly":
            return DISPLAY_AGENT_TO_FRIENDLY.get(display_name, self._slugify(display_name))
        return DISPLAY_AGENT_TO_BLOB.get(display_name, self._slugify(display_name))

    def _upload_or_emit(self, blob: Dict[str, object]) -> bool:
        payload = json.dumps(blob, indent=2, ensure_ascii=False).encode("utf-8")
        if self.config.stdout_json:
            print(payload.decode("utf-8"))
        self._write_output_json(payload)
        if self.config.dry_run or not self.config.r2_endpoint:
            return False

        for attempt in range(2):
            try:
                request = urllib.request.Request(
                    self.config.r2_endpoint,
                    data=payload,
                    method=self.config.upload_method,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=self.config.http_timeout) as response:
                    response.read()
                return True
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                print(f"[state_sync] upload failed (attempt {attempt + 1}/2): {exc}", file=sys.stderr)
                if attempt == 0 and not STOP_REQUESTED:
                    self._interruptible_sleep(self.config.retry_delay)
        return False

    def _write_output_json(self, payload: bytes) -> None:
        output_path = self.config.output_json_path
        if output_path is None:
            return

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = output_path.with_name(f"{output_path.name}.tmp")
            temp_path.write_bytes(payload)
            temp_path.replace(output_path)
        except OSError as exc:
            print(f"[state_sync] failed to write local state json: {exc}", file=sys.stderr)

    def _read_latest_commit(self) -> Dict[str, Optional[str]]:
        if not self.config.repo_path:
            return {"hash": None, "message": None, "timestamp": None}
        try:
            result = subprocess.run(
                ["git", "-C", str(self.config.repo_path), "log", "-1", "--format=%H|%s|%aI"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return {"hash": None, "message": None, "timestamp": None}

        line = result.stdout.strip()
        if not line or "|" not in line:
            return {"hash": None, "message": None, "timestamp": None}
        sha, subject, authored_at = line.split("|", 2)
        return {"hash": sha or None, "message": subject or None, "timestamp": authored_at or None}

    def _print_status(self, blob: Dict[str, object], uploaded: bool) -> None:
        pipeline = blob["pipeline"]  # type: ignore[index]
        elapsed_seconds = int(blob["elapsed_seconds"])  # type: ignore[arg-type]
        agent = pipeline.get("current_agent") or "-"  # type: ignore[union-attr]
        task_index = pipeline.get("current_task_index") or 0  # type: ignore[union-attr]
        total_tasks = pipeline.get("total_tasks") or 0  # type: ignore[union-attr]
        elapsed = self._format_duration(elapsed_seconds)
        verb = "Synced" if uploaded else "Updated"
        print(f"{verb}: task {task_index}/{total_tasks}, agent={agent}, elapsed={elapsed}")

    def _reset_parser_state(self, new_anchor_date: Optional[date] = None) -> None:
        self.offset = 0
        self.partial = ""
        anchor = new_anchor_date or self.anchor_date
        self.state = ParserState(log_lines=deque(maxlen=self.config.log_tail_size))
        self.anchor_date = anchor
        self._init_tests()

    def _init_tests(self) -> None:
        for suite in self.config.test_suites:
            self.state.tests[suite] = {"passed": 0, "failed": 0, "total": 0, "active": False}

    def _resolve_event_datetime(self, hhmmss: str) -> datetime:
        parsed_time = datetime.strptime(hhmmss, "%H:%M:%S").time()
        current_date = self.state.current_line_date or self.anchor_date or datetime.now(self.tzinfo).date()
        candidate = datetime.combine(current_date, parsed_time, tzinfo=self.tzinfo)
        if self.state.last_line_dt and candidate < self.state.last_line_dt:
            if (self.state.last_line_dt - candidate) > timedelta(hours=12):
                candidate = datetime.combine(current_date + timedelta(days=1), parsed_time, tzinfo=self.tzinfo)
                self.state.current_line_date = candidate.date()
            else:
                # Small out-of-order batches are preserved as-is.
                pass
        else:
            self.state.current_line_date = candidate.date()

        if self.state.last_line_dt is None or candidate > self.state.last_line_dt:
            self.state.last_line_dt = candidate
        return candidate

    @staticmethod
    def _split_complete_lines(raw: str) -> Tuple[List[str], str]:
        if not raw:
            return [], ""
        if raw.endswith("\n"):
            return raw.splitlines(), ""
        lines = raw.splitlines()
        if not lines:
            return [], raw
        return lines[:-1], lines[-1]

    @staticmethod
    def _format_duration(seconds: int) -> str:
        hours, rem = divmod(max(0, seconds), 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h{minutes:02d}m"
        if minutes:
            return f"{minutes}m{secs:02d}s"
        return f"{secs}s"

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")

    def _normalize_suite_name(self, value: str) -> str:
        return self._slugify(value)

    @staticmethod
    def _interruptible_sleep(seconds: float) -> None:
        deadline = time.time() + max(0.0, seconds)
        while not STOP_REQUESTED and time.time() < deadline:
            time.sleep(min(0.25, max(0.0, deadline - time.time())))

    @staticmethod
    def _load_tz(name: str):
        if ZoneInfo is None:
            return timezone.utc
        try:
            return ZoneInfo(name)
        except Exception:
            return timezone.utc

    def _initial_anchor_date(self, dashboard_log: Path) -> date:
        if dashboard_log.exists():
            return datetime.fromtimestamp(dashboard_log.stat().st_mtime, tz=self.tzinfo).date()
        return datetime.now(self.tzinfo).date()

    def _event_watch_specs(self) -> List[Tuple[Path, bool]]:
        return [(self.config.dashboard_log.parent, False)]

    def _is_relevant_event_path(self, path: Path) -> bool:
        try:
            return path.resolve() == self.config.dashboard_log.resolve()
        except OSError:
            return path.absolute() == self.config.dashboard_log.absolute()

    def _event_fingerprint(self) -> str:
        return self._fingerprint_paths((self.config.dashboard_log,))

    @staticmethod
    def _fingerprint_paths(paths: Iterable[Path]) -> str:
        digest = hashlib.blake2s(digest_size=16)
        for path in sorted({str(candidate) for candidate in paths}):
            candidate = Path(path)
            try:
                stat = candidate.stat()
            except OSError:
                digest.update(f"{path}|missing\n".encode("utf-8"))
                continue
            digest.update(
                f"{path}|{stat.st_mtime_ns}|{stat.st_size}|{stat.st_ino}\n".encode("utf-8", errors="replace")
            )
        return digest.hexdigest()


class NativeMillraceStateSync(StateSync):
    """Build the public dashboard blob from Millrace runtime artifacts."""

    def process_cycle(self) -> None:
        blob = self._build_native_state_blob()
        uploaded = self._upload_or_emit(blob)
        self._print_status(blob, uploaded=uploaded)

    def _build_native_state_blob(self) -> Dict[str, object]:
        now_utc = datetime.now(timezone.utc)
        workspace = self.config.millrace_workspace
        assert workspace is not None
        root = workspace.expanduser().resolve()
        agents = root / "millrace-agents"
        state_dir = agents / "state"
        snapshot = self._read_json(state_dir / "runtime_snapshot.json")
        compiled_plan = self._read_json(state_dir / "compiled_plan.json")
        baseline_manifest = self._read_json(state_dir / "baseline_manifest.json")
        open_targets = self._read_closure_targets(agents / "arbiter" / "targets")
        runs = self._read_runs(agents / "runs")
        latest_run = runs[-1] if runs else {}
        token_usage = self._aggregate_run_tokens(runs)
        queue_counts = self._queue_counts(agents)
        active_plane = self._string(snapshot.get("active_plane")) or self._infer_active_plane(snapshot) or "execution"
        active_stage = self._string(snapshot.get("active_stage"))
        active_work_item_id = self._string(snapshot.get("active_work_item_id"))
        active_since = self._string(snapshot.get("active_since"))
        started_at = self._string(snapshot.get("started_at"))
        published_at = now_utc.isoformat().replace("+00:00", "Z")
        snapshot_updated_at = self._string(snapshot.get("updated_at")) or published_at
        elapsed_anchor = started_at or self._earliest_started_at(runs) or active_since
        elapsed_seconds = self._elapsed_seconds(elapsed_anchor, now_utc)
        current_model = self._string(latest_run.get("model_name"))

        tasks = self._work_items_for_dashboard(agents, active_stage=active_stage)
        done_count = sum(1 for task in tasks if task.get("status") == "complete")
        active_count = sum(1 for task in tasks if task.get("status") == "active")
        total_count = len(tasks)
        current_index = done_count + (1 if active_count else 0)

        log_lines = self._native_log_lines(
            snapshot=snapshot,
            queue_counts=queue_counts,
            runs=runs,
            updated_at=snapshot_updated_at,
        )

        active_mode = self._string(snapshot.get("active_mode_id")) or self._string(compiled_plan.get("mode_id"))
        closure = {
            "open_count": len(open_targets),
            "root_spec_id": self._string(open_targets[0].get("root_spec_id")) if open_targets else None,
            "blocked_by_lineage_work": bool(open_targets[0].get("closure_blocked_by_lineage_work")) if open_targets else False,
            "latest_verdict_path": self._path_name(open_targets[0].get("latest_verdict_path")) if open_targets else None,
            "latest_report_path": self._path_name(open_targets[0].get("latest_report_path")) if open_targets else None,
        }

        return {
            "timestamp": published_at,
            "run_id": self.config.run_id,
            "elapsed_seconds": elapsed_seconds,
            "tracker": self._tracker_blob(),
            "loop": {
                "active_loop": active_plane,
                "research_mode": None,
            },
            "pipeline": {
                "current_agent": active_stage,
                "current_task_index": current_index,
                "total_tasks": total_count,
                "agent_started_at": active_since,
            },
            "tasks": tasks,
            "metrics": {
                "tokens_in": token_usage["input_tokens"],
                "tokens_out": token_usage["output_tokens"],
                "cached_tokens": token_usage["cached_input_tokens"],
                "current_model": current_model,
                "cycle_number": len(runs),
            },
            "tests": self._default_tests(),
            "latest_commit": self._read_latest_commit(),
            "log_lines": log_lines[-self.config.log_tail_size :],
            "runtime": {
                "workspace": root.name,
                "runtime_mode": self._string(snapshot.get("runtime_mode")),
                "process_running": bool(snapshot.get("process_running")),
                "paused": bool(snapshot.get("paused")),
                "stop_requested": bool(snapshot.get("stop_requested")),
                "active_mode_id": active_mode,
                "compiled_plan_id": self._string(snapshot.get("compiled_plan_id"))
                or self._string(compiled_plan.get("compiled_plan_id")),
                "compiled_plan_currentness": self._string(snapshot.get("compiled_plan_currentness")),
                "active_plane": active_plane,
                "active_stage": active_stage,
                "active_run_id": self._string(snapshot.get("active_run_id")),
                "active_work_item_kind": self._string(snapshot.get("active_work_item_kind")),
                "active_work_item_id": active_work_item_id,
                "execution_status_marker": self._string(snapshot.get("execution_status_marker")),
                "planning_status_marker": self._string(snapshot.get("planning_status_marker")),
                "learning_status_marker": self._string(snapshot.get("learning_status_marker")),
                "current_failure_class": self._string(snapshot.get("current_failure_class")),
                "watcher_mode": self._string(snapshot.get("watcher_mode")),
                "snapshot_updated_at": snapshot_updated_at,
                "elapsed_anchor_at": elapsed_anchor,
                "baseline_seed_package_version": self._string(baseline_manifest.get("seed_package_version")),
                "closure": closure,
            },
            "queues": queue_counts,
        }

    def _queue_counts(self, agents: Path) -> Dict[str, Dict[str, int]]:
        return {
            "execution": self._lane_counts(agents / "tasks", ("queue", "active", "done", "blocked")),
            "planning": self._combined_counts(
                (
                    (agents / "specs", ("queue", "active", "done", "blocked")),
                    (agents / "incidents", ("incoming", "active", "resolved", "blocked")),
                )
            ),
            "learning": self._lane_counts(
                agents / "learning" / "requests",
                ("queue", "active", "done", "blocked"),
            ),
        }

    def _combined_counts(self, sources: Tuple[Tuple[Path, Tuple[str, ...]], ...]) -> Dict[str, int]:
        combined: Dict[str, int] = {}
        for root, lanes in sources:
            for lane, count in self._lane_counts(root, lanes).items():
                normalized = "queue" if lane == "incoming" else "done" if lane == "resolved" else lane
                combined[normalized] = combined.get(normalized, 0) + count
        return combined

    @staticmethod
    def _lane_counts(root: Path, lanes: Tuple[str, ...]) -> Dict[str, int]:
        return {
            lane: len(tuple((root / lane).glob("*.md"))) if (root / lane).exists() else 0
            for lane in lanes
        }

    def _work_items_for_dashboard(self, agents: Path, *, active_stage: Optional[str]) -> List[Dict[str, object]]:
        items: List[Dict[str, object]] = []
        for lane, status in (("done", "complete"), ("active", "active"), ("queue", "pending"), ("blocked", "pending")):
            for path in sorted((agents / "tasks" / lane).glob("*.md")):
                parsed = self._parse_work_doc(path)
                entry: Dict[str, object] = {
                    "id": parsed.get("Task-ID") or path.stem,
                    "name": parsed.get("Title") or path.stem,
                    "status": status,
                }
                if status == "active" and active_stage:
                    entry["active_agent"] = active_stage
                items.append(entry)
        return items[-80:]

    def _native_log_lines(
        self,
        *,
        snapshot: Dict[str, object],
        queue_counts: Dict[str, Dict[str, int]],
        runs: List[Dict[str, object]],
        updated_at: str,
    ) -> List[str]:
        clock = self._clock(updated_at)
        active_plane = self._string(snapshot.get("active_plane")) or self._infer_active_plane(snapshot) or "execution"
        active_stage = self._string(snapshot.get("active_stage")) or "none"
        execution = queue_counts.get("execution", {})
        planning = queue_counts.get("planning", {})
        learning = queue_counts.get("learning", {})
        lines = [
            f"[{clock}] Runtime snapshot refreshed",
            f"[{clock}] Active plane: {active_plane}; stage: {active_stage}",
            (
                f"[{clock}] Queue depths: execution={self._count_total(execution)} "
                f"planning={self._count_total(planning)} learning={self._count_total(learning)}"
            ),
        ]
        if snapshot.get("current_failure_class"):
            lines.append(f"[{clock}] Failure class: {snapshot.get('current_failure_class')}")
        for run in runs[-4:]:
            stage = run.get("stage") or "stage"
            terminal = run.get("terminal_result") or run.get("status") or "result"
            work_item_id = run.get("work_item_id") or "-"
            lines.append(f"[{self._clock(self._string(run.get('completed_at')))}] {stage}: {terminal} ({work_item_id})")
        return lines

    def _read_runs(self, runs_dir: Path) -> List[Dict[str, object]]:
        runs: List[Dict[str, object]] = []
        if not runs_dir.exists():
            return runs
        for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
            stage_results = sorted((run_dir / "stage_results").glob("*.json"))
            token_usage = self._run_dir_token_usage(run_dir, stage_results)
            invocation = self._latest_json(run_dir, "runner_invocation.*.json")
            completion = self._latest_json(run_dir, "runner_completion.*.json")
            if not stage_results:
                runs.append(
                    {
                        "run_id": run_dir.name,
                        "status": "incomplete",
                        "stage": self._string(invocation.get("stage")) or self._string(completion.get("stage")),
                        "model_name": self._string(invocation.get("model_name"))
                        or self._string(completion.get("model_name")),
                        "started_at": self._string(completion.get("started_at"))
                        or self._string(invocation.get("started_at"))
                        or self._string(invocation.get("emitted_at")),
                        "completed_at": self._string(completion.get("ended_at")),
                        "token_usage": token_usage,
                    }
                )
                continue
            latest = self._read_json(stage_results[-1])
            runs.append(
                {
                    "run_id": run_dir.name,
                    "stage": self._string(latest.get("stage")),
                    "terminal_result": self._string(latest.get("terminal_result")),
                    "result_class": self._string(latest.get("result_class")),
                    "work_item_kind": self._string(latest.get("work_item_kind")),
                    "work_item_id": self._string(latest.get("work_item_id")),
                    "model_name": self._string(latest.get("model_name"))
                    or self._string(invocation.get("model_name"))
                    or self._string(completion.get("model_name")),
                    "started_at": self._string(latest.get("started_at")),
                    "completed_at": self._string(latest.get("completed_at")),
                    "token_usage": token_usage,
                }
            )
        runs.sort(key=lambda item: str(item.get("completed_at") or item.get("run_id") or ""))
        return runs

    def _event_watch_specs(self) -> List[Tuple[Path, bool]]:
        workspace = self.config.millrace_workspace
        assert workspace is not None
        agents = workspace.expanduser().resolve() / "millrace-agents"
        specs: List[Tuple[Path, bool]] = [
            (agents / "state", False),
            (agents / "runs", True),
            (agents / "tasks", True),
            (agents / "specs", True),
            (agents / "incidents", True),
            (agents / "learning", True),
            (agents / "arbiter" / "targets", True),
            (agents / "state" / "mailbox", True),
        ]
        if self.config.repo_path:
            git_dir = self.config.repo_path / ".git"
            if git_dir.exists():
                specs.append((git_dir, True))
        return specs

    def _is_relevant_event_path(self, path: Path) -> bool:
        workspace = self.config.millrace_workspace
        assert workspace is not None
        agents = workspace.expanduser().resolve() / "millrace-agents"
        absolute = path.absolute()
        parts = absolute.parts

        state_dir = agents / "state"
        if absolute.parent == state_dir and absolute.name in {
            "runtime_snapshot.json",
            "compiled_plan.json",
            "baseline_manifest.json",
            "compile_diagnostics.json",
        }:
            return True

        if "stage_results" in parts and absolute.suffix == ".json":
            return True
        if absolute.name.startswith("runner_completion.") and absolute.suffix == ".json":
            return True
        if absolute.name.startswith("runner_invocation.") and absolute.suffix == ".json":
            return True

        for root_name in ("tasks", "specs", "incidents", "learning"):
            root = agents / root_name
            if self._path_is_relative_to(absolute, root) and absolute.suffix in {".md", ".json"}:
                return True

        if self._path_is_relative_to(absolute, agents / "arbiter" / "targets") and absolute.suffix == ".json":
            return True
        if self._path_is_relative_to(absolute, agents / "state" / "mailbox") and absolute.suffix == ".json":
            return True

        if self.config.repo_path:
            git_dir = (self.config.repo_path / ".git").absolute()
            if self._path_is_relative_to(absolute, git_dir):
                return absolute.name in {"HEAD", "index", "packed-refs"} or "refs" in absolute.parts

        return False

    def _event_fingerprint(self) -> str:
        workspace = self.config.millrace_workspace
        assert workspace is not None
        agents = workspace.expanduser().resolve() / "millrace-agents"
        digest = hashlib.blake2s(digest_size=16)
        self._fingerprint_json_subset(
            digest,
            agents / "state" / "runtime_snapshot.json",
            (
                "runtime_mode",
                "process_running",
                "paused",
                "stop_requested",
                "active_mode_id",
                "compiled_plan_id",
                "active_plane",
                "active_stage",
                "active_run_id",
                "active_work_item_kind",
                "active_work_item_id",
                "execution_status_marker",
                "planning_status_marker",
                "learning_status_marker",
                "queue_depth_execution",
                "queue_depth_planning",
                "queue_depth_learning",
                "last_terminal_result",
                "last_stage_result_path",
                "current_failure_class",
                "watcher_mode",
            ),
        )
        self._fingerprint_json_subset(
            digest,
            agents / "state" / "compiled_plan.json",
            ("compiled_plan_id", "mode_id", "compile_input_fingerprint"),
        )
        self._fingerprint_json_subset(
            digest,
            agents / "state" / "baseline_manifest.json",
            ("manifest_id", "seed_package_version"),
        )
        self._fingerprint_json_subset(
            digest,
            agents / "state" / "compile_diagnostics.json",
            ("ok", "mode_id", "errors", "warnings"),
        )

        paths: List[Path] = []
        paths.extend(self._glob_files(agents / "tasks", ("*.md", "*.json")))
        paths.extend(self._glob_files(agents / "specs", ("*.md", "*.json")))
        paths.extend(self._glob_files(agents / "incidents", ("*.md", "*.json")))
        paths.extend(self._glob_files(agents / "learning", ("*.md", "*.json")))
        paths.extend(self._glob_files(agents / "arbiter" / "targets", ("*.json",)))
        paths.extend(self._glob_files(agents / "state" / "mailbox", ("*.json",)))

        runs_dir = agents / "runs"
        paths.extend(self._glob_files(runs_dir, ("stage_results/*.json",)))
        paths.extend(self._glob_files(runs_dir, ("runner_completion.*.json",)))
        paths.extend(self._glob_files(runs_dir, ("runner_invocation.*.json",)))

        if self.config.repo_path:
            git_dir = self.config.repo_path / ".git"
            paths.extend((git_dir / name for name in ("HEAD", "index", "packed-refs")))
            paths.extend(self._glob_files(git_dir / "refs", ("*",)))

        digest.update(self._fingerprint_paths(paths).encode("ascii"))
        return digest.hexdigest()

    def _fingerprint_json_subset(self, digest: "hashlib._Hash", path: Path, keys: Tuple[str, ...]) -> None:
        payload = self._read_json(path)
        subset = {key: payload.get(key) for key in keys if key in payload}
        digest.update(str(path).encode("utf-8", errors="replace"))
        digest.update(json.dumps(subset, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))

    @staticmethod
    def _glob_files(root: Path, patterns: Tuple[str, ...]) -> List[Path]:
        if not root.exists():
            return []
        files: List[Path] = []
        for pattern in patterns:
            files.extend(path for path in root.rglob(pattern) if path.is_file())
        return files

    def _run_dir_token_usage(self, run_dir: Path, stage_results: List[Path]) -> Dict[str, int]:
        stage_usage = self._sum_usage_dicts(
            self._read_json(path).get("token_usage")
            for path in stage_results
        )
        if self._has_token_usage(stage_usage):
            return stage_usage

        completion_usage = self._sum_usage_dicts(
            self._read_json(path).get("token_usage")
            for path in sorted(run_dir.glob("runner_completion.*.json"))
        )
        if self._has_token_usage(completion_usage):
            return completion_usage

        event_paths = sorted(run_dir.glob("runner_events.*.jsonl"))
        if event_paths:
            return self._sum_usage_dicts(
                usage
                for path in event_paths
                for usage in self._usage_events_from_jsonl(path)
            )

        stdout_paths = sorted(run_dir.glob("runner_stdout.*.txt"))
        return self._sum_usage_dicts(
            usage
            for path in stdout_paths
            for usage in self._usage_events_from_jsonl(path)
        )

    @staticmethod
    def _sum_usage_dicts(usages: Iterable[object]) -> Dict[str, int]:
        totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
        }
        for usage in usages:
            if not isinstance(usage, dict):
                continue
            for key in totals:
                value = usage.get(key)
                if isinstance(value, int):
                    totals[key] += max(0, value)
        return totals

    @staticmethod
    def _has_token_usage(usage: Dict[str, int]) -> bool:
        return any(value > 0 for value in usage.values())

    def _usage_events_from_jsonl(self, path: Path) -> Iterable[Dict[str, int]]:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

        usages: List[Dict[str, int]] = []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "turn.completed":
                continue
            usage = event.get("usage")
            if isinstance(usage, dict):
                usages.append(self._sum_usage_dicts((usage,)))
        return usages

    def _latest_json(self, run_dir: Path, pattern: str) -> Dict[str, object]:
        paths = sorted(run_dir.glob(pattern), key=lambda path: path.stat().st_mtime if path.exists() else 0)
        return self._read_json(paths[-1]) if paths else {}

    @staticmethod
    def _aggregate_run_tokens(runs: List[Dict[str, object]]) -> Dict[str, int]:
        totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
        }
        for run in runs:
            usage = run.get("token_usage")
            if not isinstance(usage, dict):
                continue
            for key in totals:
                value = usage.get(key)
                if isinstance(value, int):
                    totals[key] += max(0, value)
        return totals

    @staticmethod
    def _earliest_started_at(runs: List[Dict[str, object]]) -> Optional[str]:
        candidates = [run.get("started_at") for run in runs if isinstance(run.get("started_at"), str)]
        return min(candidates) if candidates else None

    def _read_closure_targets(self, targets_dir: Path) -> List[Dict[str, object]]:
        targets: List[Dict[str, object]] = []
        for path in sorted(targets_dir.glob("*.json")) if targets_dir.exists() else []:
            payload = self._read_json(path)
            if payload.get("closure_open"):
                targets.append(payload)
        return targets

    def _default_tests(self) -> Dict[str, Dict[str, object]]:
        return {
            suite: {"passed": 0, "failed": 0, "total": 0, "active": False}
            for suite in self.config.test_suites
        }

    @staticmethod
    def _parse_work_doc(path: Path) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return fields
        for line in lines:
            if line.startswith("# ") and "Title" not in fields:
                fields["Title"] = line[2:].strip()
                continue
            match = re.match(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.*?)\s*$", line)
            if match:
                fields[match.group(1)] = match.group(2)
        return fields

    @staticmethod
    def _read_json(path: Path) -> Dict[str, object]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _infer_active_plane(snapshot: Dict[str, object]) -> Optional[str]:
        for plane in ("execution", "planning", "learning"):
            marker = snapshot.get(f"{plane}_status_marker")
            if isinstance(marker, str) and marker != "### IDLE":
                return plane
        return None

    @staticmethod
    def _string(value: object) -> Optional[str]:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _path_name(value: object) -> Optional[str]:
        return Path(value).name if isinstance(value, str) and value else None

    @staticmethod
    def _count_total(counts: Dict[str, int]) -> int:
        return sum(value for value in counts.values() if isinstance(value, int))

    @staticmethod
    def _elapsed_seconds(started_at: Optional[str], now_utc: datetime) -> int:
        if not started_at:
            return 0
        try:
            parsed = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return 0
        return max(0, int((now_utc - parsed.astimezone(timezone.utc)).total_seconds()))

    @staticmethod
    def _clock(timestamp: Optional[str]) -> str:
        if not timestamp:
            return "--:--:--"
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return "--:--:--"
        return parsed.astimezone(timezone.utc).strftime("%H:%M:%S")

    @staticmethod
    def _path_is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root.absolute())
            return True
        except ValueError:
            return False


def _parse_test_suites(raw: str) -> List[str]:
    suites = [re.sub(r"[^a-z0-9_]+", "_", item.strip().lower()).strip("_") for item in raw.split(",")]
    return [suite for suite in suites if suite] or DEFAULT_TEST_SUITES[:]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_args(argv: Optional[Iterable[str]] = None) -> TrackerConfig:
    parser = argparse.ArgumentParser(description="Parse dashboard.log into a state blob and sync it to R2")
    parser.add_argument("--dashboard-log", default=os.getenv("DASHBOARD_LOG", "./dashboard.log"))
    parser.add_argument("--repo-path", default=os.getenv("REPO_PATH", ""))
    parser.add_argument(
        "--millrace-workspace",
        default=os.getenv("MILLRACE_WORKSPACE", ""),
        help=(
            "Optional Millrace workspace root. When set, state is built from "
            "<workspace>/millrace-agents instead of dashboard.log."
        ),
    )
    parser.add_argument("--r2-endpoint", default=os.getenv("R2_ENDPOINT", ""))
    parser.add_argument(
        "--output-json",
        default=os.getenv("OUTPUT_JSON_PATH", ""),
        help="Optional local file path to write the generated state blob each cycle.",
    )
    parser.add_argument("--run-id", default=os.getenv("RUN_ID", "compiler-run-001"))
    parser.add_argument("--sync-interval", type=float, default=float(os.getenv("SYNC_INTERVAL", SYNC_INTERVAL_DEFAULT)))
    parser.add_argument("--retry-delay", type=float, default=float(os.getenv("RETRY_DELAY", RETRY_DELAY_DEFAULT)))
    parser.add_argument("--http-timeout", type=float, default=float(os.getenv("HTTP_TIMEOUT", HTTP_TIMEOUT_DEFAULT)))
    parser.add_argument("--upload-method", default=os.getenv("R2_METHOD", "PUT").upper(), choices=["PUT", "POST"])
    parser.add_argument("--tracker-tz", default=os.getenv("TRACKER_TZ", "UTC"))
    parser.add_argument(
        "--agent-value-style",
        default=os.getenv("AGENT_VALUE_STYLE", DEFAULT_AGENT_VALUE_STYLE).lower(),
        choices=["blob", "friendly"],
        help="blob=start/check/integrate...; friendly=builder/qa/integrator...",
    )
    parser.add_argument(
        "--test-suites",
        default=os.getenv("TRACKER_TEST_SUITES", ",".join(DEFAULT_TEST_SUITES)),
        help="Comma-separated suite keys. Defaults are compiler-oriented.",
    )
    parser.add_argument("--log-tail-size", type=int, default=int(os.getenv("LOG_TAIL_SIZE", DEFAULT_LOG_TAIL)))
    parser.set_defaults(event_driven=_env_bool("STATE_SYNC_EVENT_DRIVEN", _env_bool("EVENT_DRIVEN", False)))
    parser.add_argument("--event-driven", dest="event_driven", action="store_true", help="Sync on filesystem events with a heartbeat.")
    parser.add_argument("--no-event-driven", dest="event_driven", action="store_false", help="Use fixed-interval sync.")
    parser.add_argument(
        "--event-debounce-seconds",
        type=float,
        default=float(os.getenv("EVENT_DEBOUNCE_SECONDS", EVENT_DEBOUNCE_DEFAULT)),
    )
    parser.add_argument(
        "--event-heartbeat-seconds",
        type=float,
        default=float(os.getenv("EVENT_HEARTBEAT_SECONDS", EVENT_HEARTBEAT_DEFAULT)),
    )
    parser.add_argument(
        "--event-check-seconds",
        type=float,
        default=float(os.getenv("EVENT_CHECK_SECONDS", EVENT_CHECK_DEFAULT)),
        help="Cheap local mtime fingerprint check interval used as a fallback when filesystem events are missed.",
    )
    parser.add_argument("--once", action="store_true", help="Run one ingest/sync cycle and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Build state but skip network upload.")
    parser.add_argument("--stdout-json", action="store_true", help="Print the JSON blob to stdout each cycle.")
    args = parser.parse_args(argv)

    repo_path = Path(args.repo_path) if args.repo_path else None
    millrace_workspace = Path(args.millrace_workspace) if args.millrace_workspace else None
    endpoint = args.r2_endpoint or None
    output_json_path = Path(args.output_json) if args.output_json else None
    return TrackerConfig(
        dashboard_log=Path(args.dashboard_log),
        repo_path=repo_path,
        millrace_workspace=millrace_workspace,
        r2_endpoint=endpoint,
        output_json_path=output_json_path,
        run_id=args.run_id,
        sync_interval=args.sync_interval,
        http_timeout=args.http_timeout,
        retry_delay=args.retry_delay,
        upload_method=args.upload_method,
        tracker_tz=args.tracker_tz,
        agent_value_style=args.agent_value_style,
        test_suites=_parse_test_suites(args.test_suites),
        log_tail_size=max(1, args.log_tail_size),
        event_driven=bool(args.event_driven),
        event_debounce_seconds=max(0.0, args.event_debounce_seconds),
        event_heartbeat_seconds=max(0.0, args.event_heartbeat_seconds),
        event_check_seconds=max(0.1, args.event_check_seconds),
        once=args.once,
        dry_run=args.dry_run,
        stdout_json=args.stdout_json,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    config = parse_args(argv)
    syncer = NativeMillraceStateSync(config) if config.millrace_workspace else StateSync(config)
    syncer.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
