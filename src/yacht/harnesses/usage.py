"""Comparable token totals from native usage fields.

Harbor documents ``n_input_tokens`` as input including cache. OMP
reports uncached ``input`` plus ``cacheRead``. Codex reports
``input_tokens`` already including ``cached_input_tokens``. Headline
tokens are that inclusive input plus output. Cache-write is not added:
it is a billing detail, not extra context. Provider fields stay raw.
"""

from __future__ import annotations

from typing import Any


def headline_tokens(usage: dict[str, Any], *, input_includes_cache: bool) -> int:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not _nonneg_int(input_tokens) or not _nonneg_int(output_tokens):
        return 0
    cache_read = usage.get("cache_read_tokens")
    if not input_includes_cache and _nonneg_int(cache_read):
        return input_tokens + cache_read + output_tokens
    return input_tokens + output_tokens


def _nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
