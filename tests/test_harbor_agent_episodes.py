import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module(name: str, relative_path: str):
    module_path = Path(__file__).resolve().parent.parent / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


episodes = _load_module(
    "yacht_harbor_agents_episodes",
    "containers/harbor-launcher/yacht_harbor_agents/episodes.py",
)
declared_support = _load_module(
    "yacht_harbor_agents_declared_support",
    "containers/harbor-launcher/yacht_harbor_agents/declared_support.py",
)


VALID_PLAN = {
    "max": 3,
    "verify_between": True,
    "instructions": ["continue one", "continue two"],
}


DECLARED_HARNESS = {
    "name": "yach",
    "prompt": "argument",
    "evidence": "file",
    "command": ["yach", "run", "--model", "{model}", "--max-turns", "{max_turns}"],
    "install": {"path": "/tmp/dist/yach", "sha256": "a" * 64},
}


class RunCommandMaxTurnsTests(unittest.TestCase):
    def test_placeholder_replaced_when_max_turns_set(self) -> None:
        command = declared_support.run_command(
            DECLARED_HARNESS,
            model="claude-haiku-4-5",
            instruction="solve it",
            max_turns=40,
        )
        self.assertIn("--max-turns 40", command)
        self.assertNotIn("{max_turns}", command)

    def test_placeholder_with_no_max_turns_raises(self) -> None:
        with self.assertRaises(declared_support.DeclaredAgentError):
            declared_support.run_command(
                DECLARED_HARNESS,
                model="claude-haiku-4-5",
                instruction="solve it",
                max_turns=None,
            )

    def test_max_turns_set_with_no_placeholder_leaves_command_unchanged(self) -> None:
        declaration = {
            **DECLARED_HARNESS,
            "command": ["yach", "run", "--model", "{model}"],
        }
        with_cap = declared_support.run_command(
            declaration,
            model="claude-haiku-4-5",
            instruction="solve it",
            max_turns=40,
        )
        without_cap = declared_support.run_command(
            declaration,
            model="claude-haiku-4-5",
            instruction="solve it",
            max_turns=None,
        )
        self.assertEqual(with_cap, without_cap)


class PlanForTaskTests(unittest.TestCase):
    def test_happy_path_returns_validated_plan(self) -> None:
        result = episodes.plan_for_task({"relay-task": VALID_PLAN}, "relay-task")
        self.assertEqual(result["max"], 3)
        self.assertTrue(result["verify_between"])
        self.assertEqual(result["instructions"], ["continue one", "continue two"])

    def test_happy_path_carries_optional_bounds(self) -> None:
        plan = dict(VALID_PLAN, max_turns=40, timeout_seconds=600)
        result = episodes.plan_for_task({"relay-task": plan}, "relay-task")
        self.assertEqual(result["max_turns"], 40)
        self.assertEqual(result["timeout_seconds"], 600)

    def test_absent_episodes_kwarg_is_not_episodic(self) -> None:
        self.assertIsNone(episodes.plan_for_task(None, "relay-task"))

    def test_task_not_in_episodes_kwarg_is_not_episodic(self) -> None:
        self.assertIsNone(
            episodes.plan_for_task({"other-task": VALID_PLAN}, "relay-task")
        )

    def test_empty_episodes_kwarg_is_not_episodic(self) -> None:
        self.assertIsNone(episodes.plan_for_task({}, "relay-task"))

    def test_max_below_two_is_malformed(self) -> None:
        plan = dict(VALID_PLAN, max=1, instructions=[])
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": plan}, "relay-task")

    def test_max_not_int_is_malformed(self) -> None:
        plan = dict(VALID_PLAN, max="3")
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": plan}, "relay-task")

    def test_instructions_length_mismatch_is_malformed(self) -> None:
        plan = dict(VALID_PLAN, instructions=["only one"])
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": plan}, "relay-task")

    def test_non_string_instruction_is_malformed(self) -> None:
        plan = dict(VALID_PLAN, instructions=["fine", 7])
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": plan}, "relay-task")

    def test_verify_between_not_bool_is_malformed(self) -> None:
        plan = dict(VALID_PLAN, verify_between="yes")
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": plan}, "relay-task")

    def test_plan_not_object_is_malformed(self) -> None:
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": "not-a-plan"}, "relay-task")

    def test_bad_max_turns_is_malformed(self) -> None:
        plan = dict(VALID_PLAN, max_turns=0)
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.plan_for_task({"relay-task": plan}, "relay-task")


class TaskIdentityTests(unittest.TestCase):
    def test_reads_task_name_and_dir_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            config = {
                "task": {"path": "/tasks/relay-task"},
                "trial_name": "relay-task__abc1234",
            }
            (trial_dir / "config.json").write_text(json.dumps(config))
            task_name, task_dir = episodes.task_identity(trial_dir)
            self.assertEqual(task_name, "relay-task")
            self.assertEqual(task_dir, Path("/tasks/relay-task"))

    def test_missing_config_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(episodes.EpisodePlanError):
                episodes.task_identity(Path(tmp))

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            (trial_dir / "config.json").write_text("{not json")
            with self.assertRaises(episodes.EpisodePlanError):
                episodes.task_identity(trial_dir)

    def test_missing_task_key_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            (trial_dir / "config.json").write_text(json.dumps({"trial_name": "x"}))
            with self.assertRaises(episodes.EpisodePlanError):
                episodes.task_identity(trial_dir)

    def test_registry_task_without_path_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            trial_dir = Path(tmp)
            config = {"task": {"name": "some-registry-task"}}
            (trial_dir / "config.json").write_text(json.dumps(config))
            with self.assertRaises(episodes.EpisodePlanError):
                episodes.task_identity(trial_dir)


RESULT_LINE_TEXT = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": []}}),
        json.dumps(
            {
                "type": "result",
                "subtype": "error_max_turns",
                "total_cost_usd": 0.42,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 10,
                    "cache_creation_input_tokens": 0,
                },
            }
        ),
    ]
)


class ParseClaudeStreamResultTests(unittest.TestCase):
    def test_parses_last_result_line(self) -> None:
        result = episodes.parse_claude_stream_result(RESULT_LINE_TEXT)
        self.assertEqual(result["subtype"], "error_max_turns")
        self.assertEqual(result["cost_usd"], 0.42)
        self.assertEqual(
            result["usage"],
            {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 0,
            },
        )

    def test_uses_last_result_line_when_multiple(self) -> None:
        text = "\n".join(
            [
                json.dumps({"type": "result", "subtype": "success"}),
                json.dumps({"type": "result", "subtype": "error_max_turns"}),
            ]
        )
        result = episodes.parse_claude_stream_result(text)
        self.assertEqual(result["subtype"], "error_max_turns")

    def test_tolerates_non_json_lines(self) -> None:
        text = "\n".join(
            [
                "not json at all {{{",
                json.dumps({"type": "result", "subtype": "success"}),
                "trailing garbage",
            ]
        )
        result = episodes.parse_claude_stream_result(text)
        self.assertEqual(result["subtype"], "success")

    def test_empty_text_returns_empty_result(self) -> None:
        result = episodes.parse_claude_stream_result("")
        self.assertEqual(result, {"subtype": None, "usage": None, "cost_usd": None})

    def test_no_result_line_returns_empty_result(self) -> None:
        text = json.dumps({"type": "system", "subtype": "init"})
        result = episodes.parse_claude_stream_result(text)
        self.assertEqual(result, {"subtype": None, "usage": None, "cost_usd": None})

    def test_negative_usage_values_are_dropped(self) -> None:
        text = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "usage": {"input_tokens": -1, "output_tokens": 50},
            }
        )
        result = episodes.parse_claude_stream_result(text)
        self.assertEqual(result["usage"], {"output_tokens": 50})

    def test_usage_with_no_valid_keys_collapses_to_none(self) -> None:
        text = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "usage": {"input_tokens": -1, "unrelated_key": 5},
            }
        )
        result = episodes.parse_claude_stream_result(text)
        self.assertIsNone(result["usage"])


class ClaudeEpisodeEndedTests(unittest.TestCase):
    def test_timeout_wins_over_everything(self) -> None:
        self.assertEqual(
            episodes.claude_episode_ended("success", True, True),
            episodes.ENDED_TIMEOUT,
        )

    def test_error_max_turns_is_cap(self) -> None:
        self.assertEqual(
            episodes.claude_episode_ended("error_max_turns", False, False),
            episodes.ENDED_CAP,
        )

    def test_success_without_error_is_natural(self) -> None:
        self.assertEqual(
            episodes.claude_episode_ended("success", False, False),
            episodes.ENDED_NATURAL,
        )

    def test_success_with_errored_flag_is_error(self) -> None:
        self.assertEqual(
            episodes.claude_episode_ended("success", False, True),
            episodes.ENDED_ERROR,
        )

    def test_other_subtype_is_error(self) -> None:
        self.assertEqual(
            episodes.claude_episode_ended("error_during_execution", False, False),
            episodes.ENDED_ERROR,
        )

    def test_none_subtype_is_error(self) -> None:
        self.assertEqual(
            episodes.claude_episode_ended(None, False, False),
            episodes.ENDED_ERROR,
        )


class OmpCodexStreamResultTests(unittest.TestCase):
    def test_parses_captured_omp_usage_and_natural_end(self) -> None:
        text = Path("tests/fixtures/omp-print-ok.jsonl").read_text(encoding="utf-8")
        result = episodes.parse_omp_stream_result(text)
        self.assertEqual(result["ended"], episodes.ENDED_NATURAL)
        self.assertEqual(
            result["usage"],
            {
                "input_tokens": 5328,
                "output_tokens": 29,
                "cache_read_tokens": 128,
                "cache_write_tokens": 0,
            },
        )
        self.assertEqual(result["cost_usd"], 0.0)

    def test_parses_captured_codex_usage_and_natural_end(self) -> None:
        text = Path("tests/fixtures/codex-exec-ok.jsonl").read_text(encoding="utf-8")
        result = episodes.parse_codex_stream_result(text)
        self.assertEqual(result["ended"], episodes.ENDED_NATURAL)
        self.assertEqual(
            result["usage"],
            {
                "input_tokens": 16583,
                "output_tokens": 5,
                "cache_read_tokens": 9984,
                "cache_write_tokens": 0,
            },
        )

    def test_parses_captured_codex_turn_failed_as_error(self) -> None:
        text = Path("tests/fixtures/codex-exec-fail.jsonl").read_text(encoding="utf-8")
        result = episodes.parse_codex_stream_result(text)
        self.assertEqual(result["ended"], episodes.ENDED_ERROR)

    def test_incomplete_omp_stream_is_unmeasured(self) -> None:
        result = episodes.parse_omp_stream_result('{"type":"agent_start"}\n')
        self.assertIsNone(result["ended"])
        self.assertIsNone(result["usage"])

    def test_malformed_line_with_valid_completion_is_unmeasured(self) -> None:
        ok = Path("tests/fixtures/codex-exec-ok.jsonl").read_text(encoding="utf-8")
        mixed = "{not json\n" + ok
        result = episodes.parse_codex_stream_result(mixed)
        self.assertIsNone(result["ended"])
        self.assertIsNone(result["usage"])

        omp = Path("tests/fixtures/omp-print-ok.jsonl").read_text(encoding="utf-8")
        result = episodes.parse_omp_stream_result("{not json\n" + omp)
        self.assertIsNone(result["ended"])
        self.assertIsNone(result["usage"])

    def test_jsonl_timeout_wins_over_natural_stream(self) -> None:
        self.assertEqual(
            episodes.jsonl_episode_ended(episodes.ENDED_NATURAL, True, False),
            episodes.ENDED_TIMEOUT,
        )

    def test_jsonl_nonzero_exit_is_error(self) -> None:
        self.assertEqual(
            episodes.jsonl_episode_ended(episodes.ENDED_NATURAL, False, True),
            episodes.ENDED_ERROR,
        )

    def test_jsonl_incomplete_stream_is_error(self) -> None:
        self.assertEqual(
            episodes.jsonl_episode_ended(None, False, False),
            episodes.ENDED_ERROR,
        )

    def test_snapshot_stream_copies_and_clears_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logs_dir = Path(temp_dir) / "agent"
            episode_dir = Path(temp_dir) / "episodes" / "001"
            logs_dir.mkdir()
            (logs_dir / "omp.jsonl").write_text(
                '{"type":"agent_end"}\n', encoding="utf-8"
            )

            text = episodes.snapshot_stream(logs_dir, episode_dir, "omp.jsonl")

            self.assertEqual(text, '{"type":"agent_end"}\n')
            self.assertEqual(
                (episode_dir / "omp.jsonl").read_text(encoding="utf-8"),
                '{"type":"agent_end"}\n',
            )
            self.assertFalse((logs_dir / "omp.jsonl").exists())


class SessionsManifestTests(unittest.TestCase):
    def test_lists_nested_jsonl_files_sorted_by_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "b.jsonl").write_text("bb")
            (root / "nested" / "a.jsonl").write_text("a")
            (root / "ignored.txt").write_text("nope")
            manifest = episodes.sessions_manifest(root)
            self.assertEqual(
                manifest,
                [
                    {"path": "b.jsonl", "size": 2},
                    {"path": "nested/a.jsonl", "size": 1},
                ],
            )

    def test_missing_dir_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            self.assertEqual(episodes.sessions_manifest(missing), [])


class ReadRewardTests(unittest.TestCase):
    def test_reads_reward_key_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.json").write_text(json.dumps({"reward": 0.75}))
            self.assertEqual(episodes.read_reward(verifier_dir), 0.75)

    def test_single_key_fallback_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.json").write_text(json.dumps({"score": 1.0}))
            self.assertEqual(episodes.read_reward(verifier_dir), 1.0)

    def test_multi_key_json_without_reward_falls_back_to_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.json").write_text(json.dumps({"a": 1.0, "b": 2.0}))
            (verifier_dir / "reward.txt").write_text("0.5")
            self.assertEqual(episodes.read_reward(verifier_dir), 0.5)

    def test_reads_bare_float_from_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.txt").write_text("1.0\n")
            self.assertEqual(episodes.read_reward(verifier_dir), 1.0)

    def test_missing_files_return_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(episodes.read_reward(Path(tmp)))

    def test_garbage_json_falls_back_to_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.json").write_text("{not json")
            (verifier_dir / "reward.txt").write_text("0.9")
            self.assertEqual(episodes.read_reward(verifier_dir), 0.9)

    def test_garbage_everywhere_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.json").write_text("{not json")
            (verifier_dir / "reward.txt").write_text("not-a-float")
            self.assertIsNone(episodes.read_reward(verifier_dir))

    def test_bool_reward_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            verifier_dir = Path(tmp)
            (verifier_dir / "reward.json").write_text(json.dumps({"reward": True}))
            self.assertIsNone(episodes.read_reward(verifier_dir))


class MergedDeclaredEvidenceTests(unittest.TestCase):
    def test_sums_usage_and_takes_last_response(self) -> None:
        per_episode = [
            {
                "schema": "yacht.harness-evidence.v1",
                "response": "first",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            {
                "schema": "yacht.harness-evidence.v1",
                "response": "second",
                "usage": {"input_tokens": 20, "output_tokens": 8},
            },
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        self.assertEqual(merged["schema"], "yacht.harness-evidence.v1")
        self.assertEqual(merged["response"], "second")
        self.assertEqual(merged["usage"]["input_tokens"], 30)
        self.assertEqual(merged["usage"]["output_tokens"], 13)

    def test_cache_read_tokens_summed_only_when_every_episode_has_it(self) -> None:
        with_cache = [
            {
                "response": "a",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 3,
                },
            },
            {
                "response": "b",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 4,
                },
            },
        ]
        merged = episodes.merged_declared_evidence(with_cache)
        self.assertEqual(merged["usage"]["cache_read_tokens"], 7)

        partial_cache = [
            {
                "response": "a",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 3,
                },
            },
            {"response": "b", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ]
        merged_partial = episodes.merged_declared_evidence(partial_cache)
        self.assertNotIn("cache_read_tokens", merged_partial["usage"])

    def test_cache_read_tokens_omitted_when_any_value_is_invalid(self) -> None:
        # A native (non-evidence_map) declared harness may emit a
        # non-integer or negative cache_read_tokens; the merge must treat
        # that episode as "not having it" (degrade, never raise) rather
        # than crash with ValueError/TypeError inside int() (final-review.md
        # Minor 2).
        invalid_type = [
            {
                "response": "a",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": "lots",
                },
            },
            {
                "response": "b",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 4,
                },
            },
        ]
        merged = episodes.merged_declared_evidence(invalid_type)
        self.assertNotIn("cache_read_tokens", merged["usage"])

        negative_value = [
            {
                "response": "a",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": -1,
                },
            },
            {
                "response": "b",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 4,
                },
            },
        ]
        merged = episodes.merged_declared_evidence(negative_value)
        self.assertNotIn("cache_read_tokens", merged["usage"])

        bool_value = [
            {
                "response": "a",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": True,
                },
            },
            {
                "response": "b",
                "usage": {
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cache_read_tokens": 4,
                },
            },
        ]
        merged = episodes.merged_declared_evidence(bool_value)
        self.assertNotIn("cache_read_tokens", merged["usage"])

    def test_cost_omitted_when_any_episode_lacks_it(self) -> None:
        per_episode = [
            {
                "response": "a",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "cost": {"total_usd": 0.1},
            },
            {"response": "b", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        self.assertNotIn("cost", merged)

    def test_cost_summed_when_every_episode_has_it(self) -> None:
        per_episode = [
            {
                "response": "a",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "cost": {"total_usd": 0.1},
            },
            {
                "response": "b",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "cost": {"total_usd": 0.2},
            },
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        self.assertAlmostEqual(merged["cost"]["total_usd"], 0.3)

    def test_tool_calls_merged_by_name(self) -> None:
        per_episode = [
            {
                "response": "a",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "tool_calls": [{"name": "bash", "count": 2}],
            },
            {
                "response": "b",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "tool_calls": [
                    {"name": "bash", "count": 1},
                    {"name": "edit", "count": 3},
                ],
            },
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        by_name = {entry["name"]: entry["count"] for entry in merged["tool_calls"]}
        self.assertEqual(by_name, {"bash": 3, "edit": 3})

    def test_tool_calls_absent_when_no_episode_has_them(self) -> None:
        per_episode = [
            {"response": "a", "usage": {"input_tokens": 1, "output_tokens": 1}}
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        self.assertNotIn("tool_calls", merged)

    def test_model_from_last_episode_that_names_one(self) -> None:
        per_episode = [
            {
                "response": "a",
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "model": "claude-a",
            },
            {"response": "b", "usage": {"input_tokens": 1, "output_tokens": 1}},
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        self.assertEqual(merged["model"], "claude-a")

    def test_empty_episode_list_raises(self) -> None:
        with self.assertRaises(episodes.EpisodePlanError):
            episodes.merged_declared_evidence([])

    def test_merged_document_satisfies_declared_support_validate_evidence(
        self,
    ) -> None:
        per_episode = [
            {
                "schema": "yacht.harness-evidence.v1",
                "response": "first",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 2,
                },
                "tool_calls": [{"name": "bash", "count": 1}],
                "model": "claude-a",
                "cost": {"total_usd": 0.1},
            },
            {
                "schema": "yacht.harness-evidence.v1",
                "response": "second",
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 8,
                    "cache_read_tokens": 3,
                },
                "tool_calls": [{"name": "edit", "count": 2}],
                "model": "claude-b",
                "cost": {"total_usd": 0.2},
            },
        ]
        merged = episodes.merged_declared_evidence(per_episode)
        # Must not raise: this is the named contract in the brief.
        declared_support.validate_evidence(merged)
        self.assertEqual(merged["schema"], declared_support.EVIDENCE_SCHEMA)


class EpisodeRecordTests(unittest.TestCase):
    def test_drops_none_fields(self) -> None:
        record = episodes.episode_record(
            index=1,
            ended=episodes.ENDED_NATURAL,
            started_at="2026-08-02T00:00:00Z",
            finished_at="2026-08-02T00:01:00Z",
        )
        self.assertEqual(
            record,
            {
                "index": 1,
                "ended": episodes.ENDED_NATURAL,
                "started_at": "2026-08-02T00:00:00Z",
                "finished_at": "2026-08-02T00:01:00Z",
            },
        )

    def test_includes_provided_optional_fields(self) -> None:
        record = episodes.episode_record(
            index=2,
            ended=episodes.ENDED_CAP,
            started_at="a",
            finished_at="b",
            usage={"input_tokens": 1},
            cost_usd=0.1,
            reward=1.0,
        )
        self.assertEqual(record["usage"], {"input_tokens": 1})
        self.assertEqual(record["cost_usd"], 0.1)
        self.assertEqual(record["reward"], 1.0)


class WriteRelaySummaryTests(unittest.TestCase):
    def test_writes_summary_with_to_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episodes_dir = Path(tmp)
            records = [
                episodes.episode_record(
                    index=1,
                    ended=episodes.ENDED_NATURAL,
                    started_at="a",
                    finished_at="b",
                )
            ]
            episodes.write_relay_summary(episodes_dir, records, 1)
            text = (episodes_dir / "summary.json").read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            payload = json.loads(text)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"], records)
            self.assertEqual(payload["to_resolution"], 1)

    def test_omits_to_resolution_when_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episodes_dir = Path(tmp)
            episodes.write_relay_summary(episodes_dir, [], None)
            payload = json.loads(
                (episodes_dir / "summary.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("to_resolution", payload)
            self.assertEqual(payload, {"count": 0, "items": []})

    def test_output_is_sorted_and_indented(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            episodes_dir = Path(tmp)
            episodes.write_relay_summary(episodes_dir, [], 3)
            text = (episodes_dir / "summary.json").read_text(encoding="utf-8")
            expected = (
                json.dumps(
                    {"count": 0, "items": [], "to_resolution": 3},
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            self.assertEqual(text, expected)


if __name__ == "__main__":
    unittest.main()
