#!/usr/bin/env python3
"""Millrace livestream tracker: raw-log -> dashboard-log aggregator.

This version keeps the loops untouched. It reads dedicated raw loop logs,
sanitizes them into dashboard-safe lines, and can enrich the public output
from repo-local Millrace artifacts when the raw stream is missing display-
ready details such as task totals, research mode, or test summaries.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

CHECK_INTERVAL_DEFAULT = 1.0
MAX_LINE_LENGTH = 120
ELLIPSIS = "…"
EM_DASH = " — "
DEFAULT_SUITE_ORDER = ("gcc_torture", "sqlite", "redis", "lua")

RAW_AGENT_TO_DISPLAY = {
    "_start.md": "Builder",
    "_integrate.md": "Integrator",
    "_check.md": "QA",
    "_hotfix.md": "Hotfix",
    "_doublecheck.md": "Doublecheck",
    "_consult.md": "Consult",
    "_troubleshoot.md": "Troubleshoot",
    "_update.md": "Update",
    "_goal_intake.md": "Goal Intake",
    "_spec_synthesis.md": "Spec Synthesis",
    "_spec_review.md": "Spec Review",
    "_critic.md": "Critic",
    "_designer.md": "Designer",
    "_taskmaster.md": "Taskmaster",
    "_taskaudit.md": "Task Audit",
    "_objective_profile_sync.md": "Objective Sync",
    "_mechanic.md": "Mechanic",
    "_incident_intake.md": "Incident Intake",
    "_incident_resolve.md": "Incident Resolve",
    "_incident_archive.md": "Incident Archive",
    "_contractor.md": "Contractor",
    "_audit_intake.md": "Audit Intake",
    "_audit_validate.md": "Audit Validate",
    "_audit_gatekeeper.md": "Audit Gatekeeper",
}
RAW_AGENT_BARE_TO_DISPLAY = {
    key[1:-3]: value
    for key, value in RAW_AGENT_TO_DISPLAY.items()
    if key.startswith("_") and key.endswith(".md")
}

DISPLAY_NAMES = set(RAW_AGENT_TO_DISPLAY.values())

KEEP_PATTERNS = [
    re.compile(r"\bStage\b.+?:\s*(?:starting|started|running|complete|completed|done)\b", re.IGNORECASE),
    re.compile(r"\bProgress:\s*\d+\s*/\s*\d+\s+tasks?\b", re.IGNORECASE),
    re.compile(r"\bTokens?:\s*in=\d+\s+out=\d+\b", re.IGNORECASE),
    re.compile(r"\b(?:status=###\s*[A-Z_]+|result=[A-Z_]+|###\s*[A-Z_]+)\b"),
    re.compile(r"\b(?:error|warn|warning|failed|blocked|needs_research|quickfix_needed|exception|traceback|escalat)\b", re.IGNORECASE),
    re.compile(r"\b(?:gcc_torture|sqlite|redis|lua|tests?|suite)\b.*\b(?:passed|failed|total|active)\b", re.IGNORECASE),
    re.compile(r"^[\w./ -]+:\s*(?:complete|completed|starting|started|running|result=)", re.IGNORECASE),
    re.compile(r"\bexit=\d+\b", re.IGNORECASE),
]

SECRET_PATTERNS = [
    re.compile(r"\b(?:api[_ -]?key|authorization|bearer|password|secret|session[_ -]?token|cookie)\b\s*[:=]", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
]

TIMESTAMP_PATTERNS = [
    re.compile(r"^\[(?P<full>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:Z)?)\]\s*(?P<body>.*)$"),
    re.compile(r"^\[(?P<time>\d{2}:\d{2}:\d{2})\]\s*(?P<body>.*)$"),
]

STATUS_LINE_RE = re.compile(
    r"^(?P<agent>[^:]+):.*?\bstatus=###\s*(?P<status>[A-Z_]+)\b(?:.*?\bexit=(?P<exit>\d+)\b)?",
    re.IGNORECASE,
)
STAGE_LINE_RE = re.compile(
    r"^Stage\s+(?P<agent>[^:]+):\s*(?P<action>starting|started|running|complete|completed|done)\b(?P<meta>.*)$",
    re.IGNORECASE,
)
SIMPLE_AGENT_EVENT_RE = re.compile(
    r"^(?P<agent>[^:]+):\s*(?P<action>complete|completed|starting|started|running)\b(?P<meta>.*)$",
    re.IGNORECASE,
)
RUNNER_START_RE = re.compile(
    r"^(?:(?:Research|Orchestrate)-)?(?P<agent>[^:]+):\s*runner=(?P<runner>[^\s]+)(?P<meta>.*)$",
    re.IGNORECASE,
)
EXIT_ONLY_RE = re.compile(r"^(?P<agent>[^:]+):.*?\bexit=(?P<exit>\d+)\b", re.IGNORECASE)
RAW_PROGRESS_RE = re.compile(r"\bProgress:\s*tasks_completed=(?P<completed>\d+)\b", re.IGNORECASE)
RAW_TASK_RE = re.compile(r'\btask=(?:"(?P<dq>[^"]+)"|\'(?P<sq>[^\']+)\')')
TOKEN_USAGE_RE = re.compile(
    r"\bToken usage:(?P<meta>.*?\binput=(?P<input>\d+)\b.*?\boutput=(?P<output>\d+)\b.*)",
    re.IGNORECASE,
)
TOKEN_CACHED_RE = re.compile(r"\bcached=(\d+)\b", re.IGNORECASE)
RESEARCH_EVENT_RE = re.compile(
    r"^-\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+\|\s+(?P<kind>[A-Z_]+)\s+\|\s*(?P<meta>.*)$"
)
RUNNER_NOTES_ESCALATION_RE = re.compile(
    r"^(?P<kind>Escalation|Task blocked|Troubleshooter outcome):\s*(?P<body>.+)$",
    re.IGNORECASE,
)
RUNNER_MODEL_RE = re.compile(r"\bmodel(?:_chain)?=([A-Za-z0-9._-]+)\b")
TASK_HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)

ABSOLUTE_PATH_RE = re.compile(r"(?:(?<=\s)|^)(?:[A-Za-z]:\\|/)[A-Za-z0-9_./\\:-]+")
INTERNAL_PATH_RE = re.compile(r"(?:(?<=\s)|^)agents/[A-Za-z0-9_./-]+")
URL_RE = re.compile(r"https?://\S+")

STOP_REQUESTED = False


def handle_signal(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


@dataclass
class TailState:
    path: Path
    offset: int = 0
    inode: Optional[int] = None
    partial: str = ""


@dataclass
class PendingOutput:
    sort_dt: datetime
    display_time: str
    source: str
    content: str


@dataclass
class RepoSnapshot:
    total_tasks: int = 0
    completed_tasks: int = 0
    active_task_name: Optional[str] = None
    research_mode: Optional[str] = None
    current_model: Optional[str] = None
    task_dt: Optional[datetime] = None
    tests_dt: Optional[datetime] = None
    research_dt: Optional[datetime] = None
    tests: Dict[str, Dict[str, object]] = field(default_factory=dict)


class Aggregator:
    def __init__(
        self,
        research_log: Path,
        orchestrate_log: Path,
        dashboard_log: Path,
        check_interval: float,
        reset_output_on_start: bool,
        start_at_end: bool = False,
        repo_root: Optional[Path] = None,
        summary_json: Optional[Path] = None,
    ) -> None:
        self.research = TailState(research_log)
        self.orchestrate = TailState(orchestrate_log)
        self.dashboard_log = dashboard_log
        self.check_interval = check_interval
        self.reset_output_on_start = reset_output_on_start
        self.start_at_end = start_at_end
        self.repo_root = repo_root
        self.summary_json = summary_json
        self.synthetic_state: Dict[str, str] = {}
        self.runner_notes_emitted: Dict[str, set[str]] = {}
        self.raw_activity_seen = False

    def prepare_output(self) -> None:
        self.dashboard_log.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if self.reset_output_on_start else "a"
        with self.dashboard_log.open(mode, encoding="utf-8"):
            pass
        if self.start_at_end:
            self._prime_tail_state(self.research)
            self._prime_tail_state(self.orchestrate)

    def run_forever(self, once: bool = False) -> None:
        self.prepare_output()
        while True:
            self.process_cycle()
            if once or STOP_REQUESTED:
                break
            self._interruptible_sleep(self.check_interval)

    def process_cycle(self) -> None:
        snapshot = self._build_repo_snapshot()
        pending: List[PendingOutput] = []
        pending.extend(self._collect_new_entries(self.research, source="RES", snapshot=snapshot))
        pending.extend(self._collect_new_entries(self.orchestrate, source="ORCH", snapshot=snapshot))
        if self.raw_activity_seen or not self.start_at_end:
            pending.extend(self._collect_runner_note_entries())
            pending.extend(self._collect_snapshot_entries(snapshot))

        if not pending:
            return

        pending.sort(key=lambda item: (item.sort_dt, 0 if item.source == "ORCH" else 1, item.content))
        with self.dashboard_log.open("a", encoding="utf-8") as handle:
            for item in pending:
                line = self._format_dashboard_line(item.display_time, item.source, item.content)
                handle.write(line + "\n")

    @staticmethod
    def _prime_tail_state(state: TailState) -> None:
        if not state.path.exists():
            return
        stat = state.path.stat()
        state.offset = stat.st_size
        state.inode = getattr(stat, "st_ino", None)
        state.partial = ""

    def _collect_new_entries(self, state: TailState, source: str, snapshot: RepoSnapshot) -> List[PendingOutput]:
        if not state.path.exists():
            return []

        stat = state.path.stat()
        inode = getattr(stat, "st_ino", None)
        truncated = stat.st_size < state.offset
        rotated = state.inode is not None and inode is not None and inode != state.inode
        if truncated or rotated:
            state.offset = 0
            state.partial = ""

        state.inode = inode
        with state.path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(state.offset)
            chunk = handle.read()
            state.offset = handle.tell()

        if not chunk:
            return []

        self.raw_activity_seen = True

        raw = state.partial + chunk
        complete_lines, state.partial = self._split_complete_lines(raw)
        now = datetime.now()
        pending: List[PendingOutput] = []
        for raw_line in complete_lines:
            parsed = self._parse_raw_line(raw_line, source=source, now=now, snapshot=snapshot)
            if parsed is not None:
                pending.append(parsed)
        return pending

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

    def _parse_raw_line(
        self,
        raw_line: str,
        source: str,
        now: datetime,
        snapshot: RepoSnapshot,
    ) -> Optional[PendingOutput]:
        stripped = raw_line.strip()
        if not stripped or self._contains_secret(stripped):
            return None

        sort_dt, display_time, body = self._extract_timestamp(raw_line, now=now)
        content = self._sanitize_body(body, source=source, snapshot=snapshot)
        if not content:
            return None
        return PendingOutput(sort_dt=sort_dt, display_time=display_time, source=source, content=content)

    def _sanitize_body(self, body: str, source: str, snapshot: RepoSnapshot) -> Optional[str]:
        text = self._normalize_space(body)
        if not text or self._contains_secret(text):
            return None

        transformed = (
            self._normalize_token_usage_line(text)
            or self._normalize_raw_progress_line(text, snapshot=snapshot)
            or self._normalize_agent_status_line(text)
            or self._normalize_runner_start_line(text, source=source, snapshot=snapshot)
            or self._normalize_stage_line(text, source=source, snapshot=snapshot)
            or self._normalize_simple_agent_event(text)
            or self._normalize_exit_only_line(text)
            or self._normalize_escalation_line(text)
            or text
        )

        transformed = self._redact_paths_and_urls(transformed)
        transformed = self._normalize_space(transformed)
        if not transformed or self._contains_secret(transformed):
            return None
        if not self._should_keep(transformed):
            return None
        return transformed

    def _normalize_token_usage_line(self, text: str) -> Optional[str]:
        match = TOKEN_USAGE_RE.search(text)
        if not match:
            return None
        cached_match = TOKEN_CACHED_RE.search(match.group("meta"))
        cached_text = f" cached={cached_match.group(1)}" if cached_match else ""
        return f"Tokens: in={match.group('input')} out={match.group('output')}{cached_text}"

    def _normalize_raw_progress_line(self, text: str, snapshot: RepoSnapshot) -> Optional[str]:
        match = RAW_PROGRESS_RE.search(text)
        if not match:
            return None
        completed = int(match.group("completed"))
        total = max(snapshot.total_tasks, completed)
        if total <= 0:
            return None
        return f"Progress: {completed}/{total} tasks"

    def _normalize_agent_status_line(self, text: str) -> Optional[str]:
        match = STATUS_LINE_RE.match(text)
        if not match:
            return None
        agent = self._display_agent(match.group("agent"))
        status = match.group("status").lstrip("#")
        if status.endswith("_COMPLETE") and status != "AUTONOMY_COMPLETE":
            return f"{agent}: complete"
        return f"{agent}: result={status}"

    def _normalize_stage_line(self, text: str, source: str, snapshot: RepoSnapshot) -> Optional[str]:
        match = STAGE_LINE_RE.match(text)
        if not match:
            return None

        agent = self._display_agent(match.group("agent"))
        action = self._normalize_action(match.group("action"))
        meta = self._clean_meta(match.group("meta"))
        if action == "starting":
            meta = self._enrich_stage_meta(meta, agent=agent, source=source, snapshot=snapshot)
        if meta:
            separator = " " if meta.startswith("(") else EM_DASH
            return f"Stage {agent}: {action}{separator}{meta}"
        return f"Stage {agent}: {action}"

    def _normalize_runner_start_line(self, text: str, source: str, snapshot: RepoSnapshot) -> Optional[str]:
        match = RUNNER_START_RE.match(text)
        if not match:
            return None

        agent = self._display_agent(match.group("agent"))
        meta = self._clean_meta(match.group("meta"))
        meta = self._enrich_stage_meta(meta, agent=agent, source=source, snapshot=snapshot)
        if meta:
            separator = " " if meta.startswith("(") else EM_DASH
            return f"Stage {agent}: starting{separator}{meta}"
        return f"Stage {agent}: starting"

    def _normalize_simple_agent_event(self, text: str) -> Optional[str]:
        if text.startswith("Stage "):
            return None
        match = SIMPLE_AGENT_EVENT_RE.match(text)
        if not match:
            return None
        agent = self._display_agent(match.group("agent"))
        action = self._normalize_action(match.group("action"))
        meta = self._clean_meta(match.group("meta"))
        if meta:
            return f"{agent}: {action}{EM_DASH}{meta}"
        return f"{agent}: {action}"

    def _normalize_exit_only_line(self, text: str) -> Optional[str]:
        match = EXIT_ONLY_RE.match(text)
        if not match:
            return None
        agent = self._display_agent(match.group("agent"))
        return f"{agent}: exit={match.group('exit')}"

    def _normalize_escalation_line(self, text: str) -> Optional[str]:
        match = RUNNER_NOTES_ESCALATION_RE.match(text)
        if not match:
            return None
        kind = match.group("kind").strip().title()
        if kind.lower() == "task blocked":
            kind = "Task blocked"
        return f"{kind}: {match.group('body').strip()}"

    def _enrich_stage_meta(self, meta: str, agent: str, source: str, snapshot: RepoSnapshot) -> str:
        parts: List[str] = [meta] if meta else []
        if source == "ORCH" and agent == "Builder" and snapshot.active_task_name and "task=" not in meta:
            parts.append(f'task="{snapshot.active_task_name}"')
        if source == "RES" and snapshot.research_mode and "mode=" not in meta:
            parts.append(f"mode={snapshot.research_mode}")
        if source == "ORCH" and snapshot.current_model and "model=" not in meta:
            parts.append(f"model={snapshot.current_model}")
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _clean_meta(meta: str) -> str:
        cleaned = meta.strip()
        cleaned = re.sub(r"^(?:[-—:|;,]+\s*)+", "", cleaned)
        cleaned = re.sub(r"\brunner=[^\s]+\b", "", cleaned)
        cleaned = re.sub(r"\bstatus=###\s*[A-Z_]+\b", "", cleaned)
        cleaned = re.sub(r"\bexit=\d+\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _normalize_action(action: str) -> str:
        lowered = action.lower()
        if lowered in {"started", "starting"}:
            return "starting"
        if lowered in {"completed", "complete", "done"}:
            return "complete"
        if lowered == "running":
            return "running"
        return lowered

    @staticmethod
    def _normalize_space(text: str) -> str:
        text = text.replace("\t", " ")
        text = text.replace("–", "—")
        return re.sub(r"\s+", " ", text).strip()

    def _should_keep(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in KEEP_PATTERNS)

    @staticmethod
    def _contains_secret(text: str) -> bool:
        return any(pattern.search(text) for pattern in SECRET_PATTERNS)

    @staticmethod
    def _extract_timestamp(raw_line: str, now: datetime) -> Tuple[datetime, str, str]:
        for pattern in TIMESTAMP_PATTERNS:
            match = pattern.match(raw_line.strip())
            if not match:
                continue
            body = match.group("body")
            full = match.groupdict().get("full")
            just_time = match.groupdict().get("time")
            if full:
                normalized = full.replace("T", " ").rstrip("Z")
                sort_dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
                return sort_dt, sort_dt.strftime("%H:%M:%S"), body
            if just_time:
                parsed_time = datetime.strptime(just_time, "%H:%M:%S").time()
                sort_dt = datetime.combine(date.today(), parsed_time)
                return sort_dt, just_time, body
        return now, now.strftime("%H:%M:%S"), raw_line.strip()

    @staticmethod
    def _display_agent(raw_agent: str) -> str:
        agent = raw_agent.strip().replace("agents/", "")
        agent = os.path.basename(agent)
        if agent in RAW_AGENT_TO_DISPLAY:
            return RAW_AGENT_TO_DISPLAY[agent]
        if agent in RAW_AGENT_BARE_TO_DISPLAY:
            return RAW_AGENT_BARE_TO_DISPLAY[agent]
        if agent in DISPLAY_NAMES:
            return agent
        if agent.startswith("_") and agent.endswith(".md"):
            slug = agent[1:-3].replace("_", " ").strip()
            return slug.title()
        return agent.strip()

    @staticmethod
    def _redact_paths_and_urls(text: str) -> str:
        redacted = URL_RE.sub("[url]", text)
        redacted = ABSOLUTE_PATH_RE.sub("[path]", redacted)
        redacted = INTERNAL_PATH_RE.sub("[internal]", redacted)
        return redacted

    @staticmethod
    def _format_dashboard_line(display_time: str, source: str, content: str) -> str:
        source_tag = "[ORCH]" if source == "ORCH" else "[RES] "
        prefix = f"[{display_time}] {source_tag} "
        max_content_len = MAX_LINE_LENGTH - len(prefix)
        if len(content) > max_content_len:
            task_match = re.search(r'task="([^"]*)"', content)
            if task_match:
                task_value = task_match.group(1)
                keep_prefix = content[: task_match.start(1)]
                keep_suffix = content[task_match.end(1) :]
                remaining = max_content_len - len(keep_prefix) - len(keep_suffix) - len(ELLIPSIS)
                if remaining > 0:
                    content = keep_prefix + task_value[:remaining] + ELLIPSIS + keep_suffix
            if len(content) > max_content_len:
                content = content[: max_content_len - len(ELLIPSIS)] + ELLIPSIS
        return prefix + content

    def _build_repo_snapshot(self) -> RepoSnapshot:
        snapshot = RepoSnapshot()
        if not self.repo_root:
            return snapshot

        snapshot.active_task_name, snapshot.total_tasks, snapshot.completed_tasks, snapshot.task_dt = self._read_task_snapshot()
        snapshot.research_mode, snapshot.research_dt = self._read_research_mode()
        snapshot.current_model = self._read_current_model()
        snapshot.tests, snapshot.tests_dt = self._read_test_snapshot()
        return snapshot

    def _read_task_snapshot(self) -> Tuple[Optional[str], int, int, Optional[datetime]]:
        agents_dir = self.repo_root / "agents"
        paths = [
            agents_dir / "tasks.md",
            agents_dir / "taskspending.md",
            agents_dir / "tasksbacklog.md",
            agents_dir / "tasksarchive.md",
        ]
        active_titles = self._read_markdown_titles(paths[0]) if paths[0].exists() else []
        pending_titles = self._read_markdown_titles(paths[1]) if paths[1].exists() else []
        backlog_titles = self._read_markdown_titles(paths[2]) if paths[2].exists() else []
        archive_titles = self._read_markdown_titles(paths[3]) if paths[3].exists() else []

        active_task_name = active_titles[0] if active_titles else None
        total_tasks = len(active_titles) + len(pending_titles) + len(backlog_titles) + len(archive_titles)
        completed_tasks = len(archive_titles)

        mtimes = [datetime.fromtimestamp(path.stat().st_mtime) for path in paths if path.exists()]
        return active_task_name, total_tasks, completed_tasks, max(mtimes) if mtimes else None

    def _read_research_mode(self) -> Tuple[Optional[str], Optional[datetime]]:
        if not self.repo_root:
            return None, None
        state_path = self.repo_root / "agents" / "research_state.json"
        if state_path.exists():
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
                mode = str(payload.get("current_mode") or "").strip().lower() or None
                return mode, datetime.fromtimestamp(state_path.stat().st_mtime)
            except (OSError, ValueError, TypeError):
                pass

        events_path = self.repo_root / "agents" / "research_events.md"
        if not events_path.exists():
            return None, None
        try:
            for line in reversed(events_path.read_text(encoding="utf-8", errors="replace").splitlines()):
                match = RESEARCH_EVENT_RE.match(line.strip())
                if not match or match.group("kind") != "MODE_DISPATCH":
                    continue
                meta = match.group("meta")
                mode_match = re.search(r"\bmode=([A-Z_]+)\b", meta)
                if not mode_match:
                    continue
                ts = datetime.strptime(match.group("ts"), "%Y-%m-%dT%H:%M:%SZ")
                return mode_match.group(1).lower(), ts
        except OSError:
            return None, None
        return None, None

    def _read_current_model(self) -> Optional[str]:
        notes_path = self._resolve_runner_notes_path()
        if not notes_path or not notes_path.exists():
            return None
        try:
            text = notes_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for line in text.splitlines():
            match = RUNNER_MODEL_RE.search(line)
            if match:
                return match.group(1)
        return None

    def _read_test_snapshot(self) -> Tuple[Dict[str, Dict[str, object]], Optional[datetime]]:
        summary_path = self._resolve_summary_json_path()
        if not summary_path or not summary_path.exists():
            return {}, None
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}, None

        tests: Dict[str, Dict[str, object]] = {}
        raw_tests = payload.get("tests")
        if isinstance(raw_tests, dict):
            for key, value in raw_tests.items():
                suite = self._normalize_suite_name(str(key))
                if not isinstance(value, dict):
                    continue
                passed = int(value.get("passed", 0) or 0)
                failed = int(value.get("failed", 0) or 0)
                total = int(value.get("total", passed + failed) or 0)
                active = bool(value.get("active", total > 0))
                tests[suite] = {"passed": passed, "failed": failed, "total": total, "active": active}
        elif isinstance(payload.get("results"), list):
            tests = self._tests_from_results_rows(payload["results"])

        return tests, datetime.fromtimestamp(summary_path.stat().st_mtime)

    def _tests_from_results_rows(self, rows: object) -> Dict[str, Dict[str, object]]:
        tests: Dict[str, Dict[str, object]] = {}
        if not isinstance(rows, list):
            return tests
        for row in rows:
            if not isinstance(row, dict):
                continue
            suite = self._normalize_suite_name(str(row.get("project") or row.get("suite") or ""))
            if not suite:
                continue
            compiler = str(row.get("compiler") or "").lower()
            if compiler and compiler != "candidate":
                continue

            if {"passed", "failed", "total"} <= set(row):
                passed = int(row.get("passed", 0) or 0)
                failed = int(row.get("failed", 0) or 0)
                total = int(row.get("total", 0) or 0)
            else:
                detail = str(row.get("detail") or "")
                score_match = re.search(r"(\d+)\s*/\s*(\d+)", detail)
                if score_match:
                    passed = int(score_match.group(1))
                    total = int(score_match.group(2))
                    failed = max(0, total - passed)
                else:
                    status = str(row.get("status") or "").upper()
                    total = 1 if status else 0
                    passed = 1 if status in {"PASS", "PASSED", "OK", "SUCCESS"} else 0
                    failed = 1 if total and not passed and status not in {"SKIP", "SKIPPED", "NOT-RUN"} else 0

            tests[suite] = {
                "passed": passed,
                "failed": failed,
                "total": total,
                "active": bool(total > 0 or row.get("active")),
            }
        return tests

    def _collect_snapshot_entries(self, snapshot: RepoSnapshot) -> List[PendingOutput]:
        pending: List[PendingOutput] = []
        if snapshot.total_tasks > 0:
            content = f"Progress: {snapshot.completed_tasks}/{snapshot.total_tasks} tasks"
            entry = self._snapshot_entry(
                key="progress",
                content=content,
                source="ORCH",
                sort_dt=snapshot.task_dt or datetime.now(),
            )
            if entry is not None:
                pending.append(entry)

        for suite in self._suite_iteration_order(snapshot.tests):
            data = snapshot.tests[suite]
            content = (
                f"Test {suite}: passed={int(data.get('passed', 0))} "
                f"failed={int(data.get('failed', 0))} total={int(data.get('total', 0))} "
                f"active={'true' if bool(data.get('active', False)) else 'false'}"
            )
            entry = self._snapshot_entry(
                key=f"test:{suite}",
                content=content,
                source="ORCH",
                sort_dt=snapshot.tests_dt or datetime.now(),
            )
            if entry is not None:
                pending.append(entry)
        return pending

    def _snapshot_entry(self, key: str, content: str, source: str, sort_dt: datetime) -> Optional[PendingOutput]:
        content = self._redact_paths_and_urls(self._normalize_space(content))
        if not content or self.synthetic_state.get(key) == content:
            return None
        self.synthetic_state[key] = content
        return PendingOutput(sort_dt=sort_dt, display_time=sort_dt.strftime("%H:%M:%S"), source=source, content=content)

    def _collect_runner_note_entries(self) -> List[PendingOutput]:
        notes_path = self._resolve_runner_notes_path()
        if not notes_path or not notes_path.exists():
            return []
        try:
            lines = notes_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []

        emitted = self.runner_notes_emitted.setdefault(str(notes_path), set())
        dt = datetime.fromtimestamp(notes_path.stat().st_mtime)
        pending: List[PendingOutput] = []
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            match = RUNNER_NOTES_ESCALATION_RE.match(stripped)
            if not match:
                continue
            fingerprint = f"{index}:{stripped}"
            if fingerprint in emitted:
                continue
            emitted.add(fingerprint)
            content = self._normalize_escalation_line(stripped)
            if not content:
                continue
            pending.append(
                PendingOutput(
                    sort_dt=dt,
                    display_time=dt.strftime("%H:%M:%S"),
                    source="ORCH",
                    content=content,
                )
            )
        return pending

    def _resolve_runner_notes_path(self) -> Optional[Path]:
        if not self.repo_root:
            return None
        runs_dir = self.repo_root / "agents" / "runs"
        if not runs_dir.exists():
            return None
        candidates = sorted(runs_dir.glob("**/runner_notes.md"), key=lambda path: path.stat().st_mtime)
        return candidates[-1] if candidates else None

    def _resolve_summary_json_path(self) -> Optional[Path]:
        if self.summary_json and self.summary_json.exists():
            return self.summary_json
        if not self.repo_root:
            return None
        candidates = [
            self.repo_root / "artifacts" / "c-harness" / "results" / "summary.json",
            self.repo_root / "results" / "summary.json",
            self.repo_root / "harness" / "results" / "summary.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _read_markdown_titles(path: Path) -> List[str]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        titles = [match.group("title").strip() for match in TASK_HEADING_RE.finditer(text)]
        return [title for title in titles if title]

    @staticmethod
    def _normalize_suite_name(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
        if slug == "gcc_torture" or slug == "gcc_torture_subset":
            return "gcc_torture"
        if slug == "gcc_torture":
            return slug
        return slug

    @staticmethod
    def _suite_iteration_order(tests: Dict[str, Dict[str, object]]) -> List[str]:
        ordered = [suite for suite in DEFAULT_SUITE_ORDER if suite in tests]
        remaining = sorted(suite for suite in tests if suite not in ordered)
        return ordered + remaining

    @staticmethod
    def _interruptible_sleep(seconds: float) -> None:
        deadline = time.time() + max(0.0, seconds)
        while not STOP_REQUESTED and time.time() < deadline:
            time.sleep(min(0.25, max(0.0, deadline - time.time())))


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Millrace raw loop logs into dashboard.log")
    parser.add_argument("--research-log", default=os.getenv("RESEARCH_LOG", "./research.log"))
    parser.add_argument("--orchestrate-log", default=os.getenv("ORCHESTRATE_LOG", "./orchestrate.log"))
    parser.add_argument("--dashboard-log", default=os.getenv("DASHBOARD_LOG", "./dashboard.log"))
    parser.add_argument("--repo-root", default=os.getenv("REPO_ROOT", ""))
    parser.add_argument("--summary-json", default=os.getenv("SUMMARY_JSON", ""))
    parser.add_argument(
        "--check-interval",
        type=float,
        default=float(os.getenv("CHECK_INTERVAL", CHECK_INTERVAL_DEFAULT)),
    )
    parser.add_argument(
        "--reset-output-on-start",
        action="store_true",
        default=os.getenv("RESET_OUTPUT_ON_START", "0") in {"1", "true", "TRUE", "yes", "YES"},
        help="Truncate dashboard.log on startup instead of appending to it.",
    )
    parser.add_argument(
        "--start-at-end",
        action="store_true",
        default=os.getenv("START_AT_END", "0") in {"1", "true", "TRUE", "yes", "YES"},
        help="Ignore pre-existing raw log content and only stream new lines written after startup.",
    )
    parser.add_argument("--once", action="store_true", help="Run one read/format/write cycle and exit.")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    args = parse_args(argv)
    repo_root = Path(args.repo_root) if args.repo_root else None
    summary_json = Path(args.summary_json) if args.summary_json else None
    aggregator = Aggregator(
        research_log=Path(args.research_log),
        orchestrate_log=Path(args.orchestrate_log),
        dashboard_log=Path(args.dashboard_log),
        check_interval=args.check_interval,
        reset_output_on_start=args.reset_output_on_start,
        start_at_end=args.start_at_end,
        repo_root=repo_root,
        summary_json=summary_json,
    )
    aggregator.run_forever(once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
