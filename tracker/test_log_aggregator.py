#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TRACK3_DIR = Path(__file__).resolve().parent
if str(TRACK3_DIR) not in sys.path:
    sys.path.insert(0, str(TRACK3_DIR))

import log_aggregator  # noqa: E402


class LogAggregatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.repo = self.root / "repo"
        self.agents = self.repo / "agents"
        self.runs = self.agents / "runs" / "2026-03-16_120000"
        self.log_dir = self.root / "logs"
        self.agents.mkdir(parents=True)
        self.runs.mkdir(parents=True)
        self.log_dir.mkdir(parents=True)

        (self.agents / "tasks.md").write_text(
            "## 2026-03-16 - Implement AST generation\n- active\n",
            encoding="utf-8",
        )
        (self.agents / "tasksbacklog.md").write_text(
            "## 2026-03-16 - Build type checker\n\n## 2026-03-16 - Add codegen smoke tests\n",
            encoding="utf-8",
        )
        (self.agents / "tasksarchive.md").write_text(
            "## 2026-03-15 - Implement lexer\n",
            encoding="utf-8",
        )
        (self.agents / "research_state.json").write_text(
            json.dumps({"current_mode": "AUDIT"}) + "\n",
            encoding="utf-8",
        )
        (self.runs / "runner_notes.md").write_text(
            "\n".join(
                [
                    "Run: 2026-03-16_120000",
                    "Builder route: model_chain=gpt-5.3-codex",
                    "Escalation: local recovery exhausted, handing to research loop",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        self.summary_json = self.root / "summary.json"
        self.summary_json.write_text(
            json.dumps(
                {
                    "tests": {
                        "gcc_torture": {"passed": 312, "failed": 18, "total": 1400, "active": True},
                        "sqlite": {"passed": 0, "failed": 0, "total": 0, "active": False},
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )

        self.research_log = self.log_dir / "research.log"
        self.orchestrate_log = self.log_dir / "orchestrate.log"
        self.dashboard_log = self.log_dir / "dashboard.log"

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _make_aggregator(self) -> log_aggregator.Aggregator:
        return log_aggregator.Aggregator(
            research_log=self.research_log,
            orchestrate_log=self.orchestrate_log,
            dashboard_log=self.dashboard_log,
            check_interval=0.01,
            reset_output_on_start=True,
            repo_root=self.repo,
            summary_json=self.summary_json,
        )

    def test_normalizes_raw_logs_and_enriches_stage_lines(self) -> None:
        self.orchestrate_log.write_text(
            "\n".join(
                [
                    "[2026-03-16 12:00:00] Stage _start.md: starting runner=codex model=gpt-5.3-codex",
                    "[2026-03-16 12:00:01] Token usage: stage=Builder input=11832 cached=5504 output=21",
                    "[2026-03-16 12:00:02] Progress: tasks_completed=2 elapsed=00h22m",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.research_log.write_text(
            "[2026-03-16 12:00:03] Stage _incident_resolve.md: starting runner=codex\n",
            encoding="utf-8",
        )

        aggregator = self._make_aggregator()
        aggregator.prepare_output()
        aggregator.process_cycle()

        output = self.dashboard_log.read_text(encoding="utf-8")
        self.assertIn('Stage Builder: starting', output)
        self.assertIn('task="2026-03-16 - Implement AST generation"', output)
        self.assertIn('model=gpt-5.3-codex', output)
        self.assertIn('Tokens: in=11832 out=21 cached=5504', output)
        self.assertIn('Progress: 2/4 tasks', output)
        self.assertIn('Stage Incident Resolve: starting', output)
        self.assertIn('mode=audit', output)

    def test_normalizes_runner_start_lines_into_stage_start_events(self) -> None:
        self.research_log.write_text(
            "[2026-03-16 12:00:03] Research-goal_intake: runner=codex model=gpt-5.3-codex effort=high search=false timeout=5400s\n",
            encoding="utf-8",
        )
        self.orchestrate_log.write_text(
            "[2026-03-16 12:00:04] Builder: runner=codex model=gpt-5.4 task=\"Build local Git object store\"\n",
            encoding="utf-8",
        )

        aggregator = self._make_aggregator()
        aggregator.prepare_output()
        aggregator.process_cycle()

        output = self.dashboard_log.read_text(encoding="utf-8")
        self.assertIn("Stage Goal Intake: starting", output)
        self.assertIn("mode=audit", output)
        self.assertIn("Stage Builder: starting", output)
        self.assertIn('task="Build local Git object store"', output)
        self.assertIn("model=gpt-5.4", output)

    def test_emits_snapshot_progress_tests_and_runner_note_escalation(self) -> None:
        self.orchestrate_log.write_text("", encoding="utf-8")
        self.research_log.write_text("", encoding="utf-8")

        aggregator = self._make_aggregator()
        aggregator.prepare_output()
        aggregator.process_cycle()
        first = self.dashboard_log.read_text(encoding="utf-8")

        self.assertIn("Progress: 1/4 tasks", first)
        self.assertIn("Test gcc_torture: passed=312 failed=18 total=1400 active=true", first)
        self.assertIn("Test sqlite: passed=0 failed=0 total=0 active=false", first)
        self.assertIn("Escalation: local recovery exhausted, handing to research loop", first)

        aggregator.process_cycle()
        second = self.dashboard_log.read_text(encoding="utf-8")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
