import unittest
from pathlib import Path

from yacht.harnesses.omp import parse_omp_jsonl

OK_FIXTURE = Path("tests/fixtures/omp-print-ok.jsonl")
TOOL_FIXTURE = Path("tests/fixtures/omp-tool-read.jsonl")


class OmpJsonlParserTests(unittest.TestCase):
    def test_parses_captured_print_stream(self) -> None:
        parsed = parse_omp_jsonl(OK_FIXTURE.read_text(encoding="utf-8"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["response"], "OK")
        self.assertEqual(
            parsed["usage"],
            {
                "input_tokens": 5328,
                "output_tokens": 29,
                "cache_read_tokens": 128,
                "cache_write_tokens": 0,
            },
        )
        self.assertEqual(parsed["cost"], {"total_usd": 0.0})
        self.assertEqual(parsed["model"], "grok-4.6")
        self.assertEqual(parsed["provider"], "xai-oauth")
        self.assertEqual(parsed["usage_source"], "reported")
        self.assertEqual(parsed["skill_stages"], ())
        self.assertEqual(parsed["ended"], "natural")

    def test_parses_captured_tool_execution(self) -> None:
        parsed = parse_omp_jsonl(TOOL_FIXTURE.read_text(encoding="utf-8"))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["tool_calls"], ("read",))
        self.assertEqual(parsed["response"], "OK")
        self.assertEqual(parsed["skill_stages"], ())

    def test_empty_stdout_from_process_failure_is_unmeasured(self) -> None:
        # Captured `omp --model definitely-not-a-real-model` wrote no JSONL
        # and exited 1. Process exit belongs to the adapter; the parser
        # sees an empty stream.
        self.assertIsNone(parse_omp_jsonl(""))

    def test_unrecognized_stream_is_unmeasured(self) -> None:
        self.assertIsNone(parse_omp_jsonl("not json at all"))
        self.assertIsNone(parse_omp_jsonl(""))
        self.assertIsNone(parse_omp_jsonl('{"type":"turn.completed"}\n'))

    def test_truncated_captured_stream_is_unmeasured(self) -> None:
        text = OK_FIXTURE.read_text(encoding="utf-8")
        self.assertIsNone(parse_omp_jsonl(text[:40]))

    def test_incomplete_valid_stream_is_unmeasured(self) -> None:
        self.assertIsNone(parse_omp_jsonl('{"type":"agent_start"}\n'))
        self.assertIsNone(
            parse_omp_jsonl('{"type":"session","version":3}\n{"type":"agent_start"}\n')
        )

    def test_terminal_event_alone_is_unmeasured(self) -> None:
        self.assertIsNone(parse_omp_jsonl('{"type":"agent_end"}\n'))


if __name__ == "__main__":
    unittest.main()
