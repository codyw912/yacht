import unittest

from yacht.serve.collection import VesselRecord
from yacht.serve.query import (
    FACET_KEYS,
    UNKNOWN_GROUP,
    facet_values,
    filter_records,
    group_records,
    record_facets,
)
from yacht.domain.model import ConfigError


def _record(
    vessel: str,
    *,
    harness: str | None = "claude-code",
    harness_version: str | None = "2.1.211",
    model: str | None = "claude-haiku-4-5",
    resolved: str | None = "claude-haiku-4-5-20251001",
    tools: list[dict] | None = None,
) -> VesselRecord:
    provenance = {
        "yacht": {"version": "0.2.0"},
        "harness": {"name": harness, "version": harness_version},
        "model": {"configured": model, "resolved": resolved},
        "runtime": {
            "backend": "container",
            "image": "yacht/claude-code-runtime:claude-2.1.211",
        },
        "tools": tools or [],
        "mixed": [],
    }
    return VesselRecord(
        logbook="/tmp/run-1",
        regatta="regatta",
        course="course",
        comparison="a-vs-b",
        vessel=vessel,
        status="measured",
        provenance=provenance,
    )


class RecordFacetsTests(unittest.TestCase):
    def test_derives_hierarchical_facet_values(self) -> None:
        record = _record(
            "rigged",
            tools=[
                {
                    "name": "fff-mcp",
                    "tools": ["fff"],
                    "version": "0.3.0",
                    "source": "npm:@ff-labs/mcp-fff@0.3.0",
                }
            ],
        )

        facets = record_facets(record)

        self.assertEqual(facets["harness"], ("claude-code",))
        self.assertEqual(facets["harness.version"], ("claude-code 2.1.211",))
        self.assertEqual(facets["model"], ("claude-haiku-4-5",))
        self.assertEqual(facets["model.resolved"], ("claude-haiku-4-5-20251001",))
        self.assertEqual(facets["backend"], ("container",))
        self.assertEqual(facets["tool"], ("fff-mcp",))
        self.assertEqual(facets["tool.version"], ("fff-mcp@0.3.0",))

    def test_null_leaves_yield_no_facet_values(self) -> None:
        record = _record("mixed", harness_version=None, resolved=None)

        facets = record_facets(record)

        self.assertEqual(facets["harness"], ("claude-code",))
        self.assertEqual(facets["harness.version"], ())
        self.assertEqual(facets["model.resolved"], ())

    def test_record_without_provenance_has_no_facet_values(self) -> None:
        record = VesselRecord(
            logbook="/tmp/run-1",
            regatta="regatta",
            course="course",
            comparison="a-vs-b",
            vessel="legacy",
            status="measured",
        )

        facets = record_facets(record)

        self.assertTrue(all(values == () for values in facets.values()))
        self.assertEqual(set(facets), set(FACET_KEYS))


class FilterRecordsTests(unittest.TestCase):
    def test_name_filter_matches_across_versions(self) -> None:
        records = [
            _record("old", harness_version="2.1.211"),
            _record("new", harness_version="2.2.0"),
            _record("other", harness="pi", harness_version="0.74.0"),
        ]

        matched = filter_records(records, {"harness": "claude-code"})

        self.assertEqual([record.vessel for record in matched], ["old", "new"])

    def test_version_filter_matches_exactly(self) -> None:
        records = [
            _record("old", harness_version="2.1.211"),
            _record("new", harness_version="2.2.0"),
            _record("mixed", harness_version=None),
        ]

        matched = filter_records(records, {"harness.version": "claude-code 2.1.211"})

        self.assertEqual([record.vessel for record in matched], ["old"])

    def test_filters_combine_conjunctively(self) -> None:
        records = [
            _record("match"),
            _record("wrong-model", model="claude-sonnet-5", resolved=None),
        ]

        matched = filter_records(
            records,
            {"harness": "claude-code", "model": "claude-haiku-4-5"},
        )

        self.assertEqual([record.vessel for record in matched], ["match"])

    def test_mixed_record_never_matches_version_exact_filter(self) -> None:
        records = [_record("mixed", harness_version=None)]

        self.assertEqual(
            filter_records(records, {"harness.version": "claude-code 2.1.211"}),
            [],
        )

    def test_rejects_unknown_facet_key(self) -> None:
        with self.assertRaisesRegex(ConfigError, "unsupported provenance facet"):
            filter_records([], {"harness.minor": "2.1"})


class GroupRecordsTests(unittest.TestCase):
    def test_groups_by_facet_with_unknown_bucket_last(self) -> None:
        records = [
            _record("a", harness_version="2.1.211"),
            _record("b", harness_version="2.2.0"),
            _record("legacy", harness=None, harness_version=None),
        ]

        groups = group_records(records, "harness.version")

        self.assertEqual(
            list(groups),
            ["claude-code 2.1.211", "claude-code 2.2.0", UNKNOWN_GROUP],
        )
        self.assertEqual([r.vessel for r in groups[UNKNOWN_GROUP]], ["legacy"])

    def test_multi_valued_facets_place_record_in_each_group(self) -> None:
        record = _record(
            "two-tools",
            tools=[
                {"name": "one", "tools": [], "version": "1.0.0", "source": None},
                {"name": "two", "tools": [], "version": "2.0.0", "source": None},
            ],
        )

        groups = group_records([record], "tool")

        self.assertEqual(set(groups), {"one", "two"})

    def test_facet_values_counts_exclude_unknown(self) -> None:
        records = [
            _record("a", harness_version="2.1.211"),
            _record("b", harness_version="2.1.211"),
            _record("legacy", harness=None, harness_version=None),
        ]

        values = facet_values(records, "harness.version")

        self.assertEqual(values, [("claude-code 2.1.211", 2)])


if __name__ == "__main__":
    unittest.main()
