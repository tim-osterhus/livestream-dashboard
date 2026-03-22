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
import json
import os
import re
import signal
import subprocess
import sys
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

SYNC_INTERVAL_DEFAULT = 60.0
RETRY_DELAY_DEFAULT = 5.0
HTTP_TIMEOUT_DEFAULT = 10.0
DEFAULT_TEST_SUITES = ["gcc_torture", "sqlite", "redis", "lua"]
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
        while True:
            self.process_cycle()
            if self.config.once or STOP_REQUESTED:
                break
            self._interruptible_sleep(self.config.sync_interval)

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


def _parse_test_suites(raw: str) -> List[str]:
    suites = [re.sub(r"[^a-z0-9_]+", "_", item.strip().lower()).strip("_") for item in raw.split(",")]
    return [suite for suite in suites if suite] or DEFAULT_TEST_SUITES[:]


def parse_args(argv: Optional[Iterable[str]] = None) -> TrackerConfig:
    parser = argparse.ArgumentParser(description="Parse dashboard.log into a state blob and sync it to R2")
    parser.add_argument("--dashboard-log", default=os.getenv("DASHBOARD_LOG", "./dashboard.log"))
    parser.add_argument("--repo-path", default=os.getenv("REPO_PATH", ""))
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
    parser.add_argument("--once", action="store_true", help="Run one ingest/sync cycle and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Build state but skip network upload.")
    parser.add_argument("--stdout-json", action="store_true", help="Print the JSON blob to stdout each cycle.")
    args = parser.parse_args(argv)

    repo_path = Path(args.repo_path) if args.repo_path else None
    endpoint = args.r2_endpoint or None
    output_json_path = Path(args.output_json) if args.output_json else None
    return TrackerConfig(
        dashboard_log=Path(args.dashboard_log),
        repo_path=repo_path,
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
        once=args.once,
        dry_run=args.dry_run,
        stdout_json=args.stdout_json,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    config = parse_args(argv)
    syncer = StateSync(config)
    syncer.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
