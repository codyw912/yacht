import unittest
from pathlib import Path

from yacht.harnesses.codex import parse_codex_jsonl


OK_FIXTURE = Path("tests/fixtures/codex-exec-ok.jsonl")
TOOL_FIXTURE = Path("tests/fixtures/codex-exec-tool.jsonl")
FAIL_FIXTURE = Path("tests/fixtures/codex-exec-fail.jsonl")


class CodexJsonlParserTests(unittest.TestCase):
    def test_parses_captured_exec_stream(self) -> None:
        parsed = parse_codex_jsonl(OK_FIXTURE.read_text(encoding="utf-8"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["response"], "OK")
        self.assertEqual(
            parsed["usage"],
            {
                "input_tokens": 16583,
                "output_tokens": 5,
                "cache_read_tokens": 9984,
                "cache_write_tokens": 0,
            },
        )
        self.assertNotIn("cost", parsed)
        self.assertEqual(parsed["usage_source"], "reported")
        self.assertEqual(parsed["ended"], "natural")
        self.assertEqual(parsed["skill_stages"], ())

    def test_parses_captured_command_execution(self) -> None:
        parsed = parse_codex_jsonl(TOOL_FIXTURE.read_text(encoding="utf-8"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["response"], "OK")
        self.assertEqual(parsed["tool_calls"], ("command_execution",))
        self.assertEqual(parsed["ended"], "natural")

    def test_parses_captured_turn_failed(self) -> None:
        parsed = parse_codex_jsonl(FAIL_FIXTURE.read_text(encoding="utf-8"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["ended"], "error")
        self.assertEqual(parsed["usage_source"], "unreported")
        self.assertEqual(parsed["skill_stages"], ())

    def test_unrecognized_stream_is_unmeasured(self) -> None:
        self.assertIsNone(parse_codex_jsonl("not json at all"))
        self.assertIsNone(parse_codex_jsonl(""))
        self.assertIsNone(parse_codex_jsonl('{"type":"agent_start"}\n'))

    def test_truncated_captured_stream_is_unmeasured(self) -> None:
        text = OK_FIXTURE.read_text(encoding="utf-8")
        self.assertIsNone(parse_codex_jsonl(text[:40]))

    def test_incomplete_valid_stream_is_unmeasured(self) -> None:
        self.assertIsNone(parse_codex_jsonl('{"type":"turn.started"}\n'))
        self.assertIsNone(
            parse_codex_jsonl(
                '{"type":"thread.started","thread_id":"fixture-thread"}\n'
                '{"type":"turn.started"}\n'
            )
        )

    def test_terminal_event_alone_is_unmeasured(self) -> None:
        self.assertIsNone(parse_codex_jsonl('{"type":"turn.completed"}\n'))


if __name__ == "__main__":
    unittest.main()
