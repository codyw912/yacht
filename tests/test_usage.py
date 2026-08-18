import unittest

from yacht.harnesses.codex import _tokens as codex_tokens
from yacht.harnesses.omp import _tokens as omp_tokens
from yacht.harnesses.usage import headline_tokens


class HeadlineTokensTests(unittest.TestCase):
    def test_omp_adds_cache_read_into_inclusive_input(self) -> None:
        self.assertEqual(
            headline_tokens(
                {
                    "input_tokens": 3,
                    "output_tokens": 153,
                    "cache_read_tokens": 15337,
                    "cache_write_tokens": 0,
                },
                input_includes_cache=False,
            ),
            15493,
        )

    def test_codex_does_not_add_cache_already_in_input(self) -> None:
        self.assertEqual(
            headline_tokens(
                {
                    "input_tokens": 48808,
                    "output_tokens": 718,
                    "cache_read_tokens": 38592,
                    "cache_write_tokens": 10201,
                },
                input_includes_cache=True,
            ),
            49526,
        )

    def test_missing_counts_are_zero(self) -> None:
        self.assertEqual(headline_tokens({}, input_includes_cache=False), 0)
        self.assertEqual(
            headline_tokens({"input_tokens": 4}, input_includes_cache=True),
            0,
        )


class AdapterHeadlineTokensTests(unittest.TestCase):
    def test_omp_adapter_adds_cache_read_not_write(self) -> None:
        self.assertEqual(
            omp_tokens(
                {
                    "usage": {
                        "input_tokens": 3,
                        "output_tokens": 153,
                        "cache_read_tokens": 15337,
                        "cache_write_tokens": 99,
                    }
                }
            ),
            15493,
        )

    def test_codex_adapter_does_not_add_cache_already_in_input(self) -> None:
        self.assertEqual(
            codex_tokens(
                {
                    "usage": {
                        "input_tokens": 48808,
                        "output_tokens": 718,
                        "cache_read_tokens": 38592,
                        "cache_write_tokens": 10201,
                    }
                }
            ),
            49526,
        )
