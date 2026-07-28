"""Export benchmark scorecards to the Every Eval Ever schema (ADR 0020).

The export is a rendering of artifacts already in the logbook, pinned to
one schema version. Its unit of record is a model, while yacht's is a
paired comparison between vessels, so each vessel becomes its own
document and the pairing it belongs to travels as context — never as a
score of its own.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from yacht.courses.handoff import COURSE_HANDOFF_PATH
from yacht.domain.model import ConfigError
from yacht.logbook.index import RUN_INDEX_PATH
from yacht.logbook.io import load_json_object, write_json
from yacht.reports.benchmark_scorecard import BENCHMARK_SCORECARD_PATH
from yacht.reports.statistics import CONFIDENCE_LEVEL, wilson_interval
from yacht.reports.task_attempt_scorecard import TASK_ATTEMPT_SCORECARD_PATH
from yacht.contracts.schemas import (
    EVERY_EVAL_EVER_INSTANCE_SCHEMA_VERSION,
    EVERY_EVAL_EVER_SCHEMA_VERSION,
    validate_every_eval_ever_document,
    validate_every_eval_ever_instance_row,
)


EVAL_LIBRARY_NAME = "yacht"
METRIC_ID = "pass_rate"


def write_every_eval_ever_export(
    *,
    logbook_dir: Path,
    output_dir: Path,
    retrieved_timestamp: str,
) -> dict[str, Any]:
    """Write one aggregate JSON and instance JSONL per vessel."""
    exports = build_every_eval_ever_export(
        logbook_dir=logbook_dir,
        retrieved_timestamp=retrieved_timestamp,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for export in exports:
        document = export["document"]
        rows = export["rows"]
        stem = _file_stem(str(document["evaluation_id"]))
        instance_path = output_dir / f"{stem}.jsonl"
        _write_jsonl(instance_path, rows)
        document["detailed_evaluation_results"] = _detailed_reference(
            instance_path,
            rows,
        )
        validate_every_eval_ever_document(document)
        aggregate_path = output_dir / f"{stem}.json"
        write_json(aggregate_path, document)
        written.append(
            {
                "evaluation_id": document["evaluation_id"],
                "vessel": export["vessel"],
                "comparison": export["comparison"],
                "aggregate_path": str(aggregate_path),
                "instance_path": str(instance_path),
                "instance_rows": len(rows),
            }
        )
    return {
        "schema_version": EVERY_EVAL_EVER_SCHEMA_VERSION,
        "output_dir": str(output_dir),
        "exports": written,
    }


def build_every_eval_ever_export(
    *,
    logbook_dir: Path,
    retrieved_timestamp: str,
) -> list[dict[str, Any]]:
    handoff = _load(logbook_dir / COURSE_HANDOFF_PATH, "course handoff artifact")
    scorecard = _load(
        logbook_dir / BENCHMARK_SCORECARD_PATH,
        "benchmark scorecard artifact",
    )
    attribution = handoff.get("export")
    if not isinstance(attribution, dict):
        raise ConfigError(
            "Every Eval Ever export requires publisher attribution, which "
            "yacht cannot observe from a run. Declare it in the regatta "
            "config and re-run:\n"
            "  [export]\n"
            '  source_organization_name = "<your org>"\n'
            '  evaluator_relationship = "first_party"  '
            "# or third_party, collaborative, other"
        )
    attempts = _optional_load(
        logbook_dir / TASK_ATTEMPT_SCORECARD_PATH,
        "task attempt scorecard artifact",
    )
    run_timestamp = _run_timestamp(logbook_dir)
    usage_by_vessel = _usage_by_comparison_and_vessel(attempts)

    exports = []
    for comparison in scorecard["comparisons"]:
        comparison_name = str(comparison["name"])
        vessels = comparison["vessels"]
        for index, vessel in enumerate(vessels):
            if str(vessel["status"]) == "missing":
                continue
            other = vessels[1 - index] if len(vessels) == 2 else None
            usage = usage_by_vessel.get((comparison_name, str(vessel["name"])))
            exports.append(
                _vessel_export(
                    handoff=handoff,
                    scorecard=scorecard,
                    comparison=comparison,
                    vessel=vessel,
                    other=other,
                    usage=usage,
                    attribution=attribution,
                    run_timestamp=run_timestamp,
                    retrieved_timestamp=retrieved_timestamp,
                    logbook_dir=logbook_dir,
                )
            )
    if not exports:
        raise ConfigError(
            "Every Eval Ever export found no measured vessels in the "
            "benchmark scorecard"
        )
    return exports


def _vessel_export(
    *,
    handoff: dict[str, Any],
    scorecard: dict[str, Any],
    comparison: dict[str, Any],
    vessel: dict[str, Any],
    other: dict[str, Any] | None,
    usage: dict[str, Any] | None,
    attribution: dict[str, Any],
    run_timestamp: str | None,
    retrieved_timestamp: str,
    logbook_dir: Path,
) -> dict[str, Any]:
    vessel_name = str(vessel["name"])
    recorded = str(vessel["status"]) == "recorded"
    provenance = _vessel_provenance(vessel, usage)
    model_id = _model_id(provenance, vessel_name)
    course = str(handoff["course"])
    evaluation_id = f"{course}/{model_id}/{vessel_name}/{retrieved_timestamp}"
    # A recorded baseline was measured in an earlier run; dating it with
    # this run's timestamp would misreport when it was measured.
    measured_at = (
        _baseline_run_date(vessel) if recorded else run_timestamp
    ) or run_timestamp

    document: dict[str, Any] = {
        "schema_version": EVERY_EVAL_EVER_SCHEMA_VERSION,
        "evaluation_id": evaluation_id,
        "retrieved_timestamp": retrieved_timestamp,
        "source_metadata": _source_metadata(attribution, handoff),
        "eval_library": _eval_library(),
        "model_info": _model_info(model_id, provenance, vessel, usage),
        "evaluation_results": [
            _evaluation_result(
                handoff=handoff,
                comparison=comparison,
                vessel=vessel,
                other=other,
                provenance=provenance,
                measured_at=measured_at,
                recorded=recorded,
            )
        ],
    }
    if measured_at is not None:
        document["evaluation_timestamp"] = measured_at
    rows = _instance_rows(
        evaluation_id=evaluation_id,
        model_id=model_id,
        course=course,
        vessel=vessel,
        comparison=comparison,
        logbook_dir=logbook_dir,
    )
    return {
        "document": document,
        "rows": rows,
        "vessel": vessel_name,
        "comparison": str(comparison["name"]),
    }


def _source_metadata(
    attribution: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        # yacht only ever reports runs it executed itself.
        "source_type": "evaluation_run",
        "source_organization_name": str(attribution["source_organization_name"]),
        "evaluator_relationship": str(attribution["evaluator_relationship"]),
        "source_name": str(attribution.get("source_name") or handoff["regatta"]),
    }
    url = attribution.get("source_organization_url")
    if isinstance(url, str) and url:
        metadata["source_organization_url"] = url
    return metadata


def _eval_library() -> dict[str, Any]:
    from yacht import __version__

    return {"name": EVAL_LIBRARY_NAME, "version": __version__}


def _model_info(
    model_id: str,
    provenance: dict[str, Any] | None,
    vessel: dict[str, Any],
    usage: dict[str, Any] | None,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": model_id.rsplit("/", 1)[-1],
        "id": model_id,
    }
    developer = model_id.rsplit("/", 1)[0] if "/" in model_id else None
    if developer:
        info["developer"] = developer
    # The vessel, not the bare model, is what was measured: two rows can
    # share a model id and differ entirely in scaffold.
    details: dict[str, str] = {"yacht_vessel": str(vessel["name"])}
    if provenance is not None:
        for key, path in (
            ("harness", ("harness", "name")),
            ("harness_version", ("harness", "version")),
            ("resolved_model", ("model", "resolved")),
            ("runtime_backend", ("runtime", "backend")),
            ("runtime_image", ("runtime", "image")),
        ):
            value = _leaf(provenance, path)
            if value is not None:
                details[key] = value
        tools = _tool_labels(provenance)
        if tools:
            details["tools"] = ", ".join(tools)
    if usage is not None:
        delivery = _delivery_labels(usage)
        if delivery:
            details["skill_delivery"] = "; ".join(delivery)
    info["additional_details"] = details
    return info


def _evaluation_result(
    *,
    handoff: dict[str, Any],
    comparison: dict[str, Any],
    vessel: dict[str, Any],
    other: dict[str, Any] | None,
    provenance: dict[str, Any] | None,
    measured_at: str | None,
    recorded: bool,
) -> dict[str, Any]:
    resolved = int(vessel["resolved_instances"])
    submitted = int(vessel["submitted_instances"])
    result: dict[str, Any] = {
        "evaluation_result_id": f"{comparison['name']}/{vessel['name']}/{METRIC_ID}",
        "evaluation_name": str(handoff["course"]),
        "source_data": _source_data(handoff, vessel),
        "metric_config": _metric_config(handoff),
        "score_details": _score_details(resolved, submitted),
    }
    if measured_at is not None:
        result["evaluation_timestamp"] = measured_at
    generation_config = _generation_config(provenance)
    if generation_config is not None:
        result["generation_config"] = generation_config
    result["additional_details"] = _result_context(
        comparison=comparison,
        vessel=vessel,
        other=other,
        recorded=recorded,
    )
    return result


def _metric_config(handoff: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric_id": METRIC_ID,
        "metric_name": "Pass rate",
        "metric_kind": METRIC_ID,
        "metric_unit": "proportion",
        "evaluation_description": (
            f"Fraction of {handoff['course']} tasks resolved, graded by the "
            f"{handoff['adapter']['kind']} harness"
        ),
        "lower_is_better": False,
        "score_type": "continuous",
        "min_score": 0.0,
        "max_score": 1.0,
    }


def _score_details(resolved: int, submitted: int) -> dict[str, Any]:
    score_details: dict[str, Any] = {
        "score": resolved / submitted if submitted else 0.0,
        "details": {
            "resolved_instances": str(resolved),
            "submitted_instances": str(submitted),
        },
    }
    interval = wilson_interval(resolved, submitted)
    if interval is not None:
        score_details["uncertainty"] = {
            "confidence_interval": {
                "lower": interval["low"],
                "upper": interval["high"],
                "confidence_level": CONFIDENCE_LEVEL,
                "method": "wilson",
            }
        }
    return score_details


def _source_data(handoff: dict[str, Any], vessel: dict[str, Any]) -> dict[str, Any]:
    adapter = handoff["adapter"]
    kind = str(adapter["kind"])
    dataset = str(adapter["dataset"])
    split = str(adapter["split"])
    sample_ids = _sample_ids(vessel)
    if kind == "custom-eval":
        # User-authored task directories are not public datasets; the
        # content digest is what makes the run identifiable at all.
        details = {"yacht_course_kind": kind, "split": split}
        digest = adapter.get("content_digest")
        if isinstance(digest, str) and digest:
            details["content_digest"] = digest
        return {
            "dataset_name": Path(dataset).name or dataset,
            "source_type": "other",
            "additional_details": details,
        }
    source: dict[str, Any] = {
        "dataset_name": dataset,
        "source_type": "hf_dataset",
        "hf_repo": dataset,
        "hf_split": split,
    }
    if sample_ids:
        source["samples_number"] = len(sample_ids)
        source["sample_ids"] = sample_ids
    details = {"yacht_course_kind": kind}
    for key in ("start_date", "end_date"):
        value = adapter.get(key)
        if isinstance(value, str) and value:
            details[key] = value
    source["additional_details"] = details
    return source


def _result_context(
    *,
    comparison: dict[str, Any],
    vessel: dict[str, Any],
    other: dict[str, Any] | None,
    recorded: bool,
) -> dict[str, str]:
    """The comparison this score belongs to, as context only.

    A treatment effect is not a benchmark result: the delta is recorded
    here so a reader can see what this vessel was compared against, and
    is never exported as a score of its own.
    """
    context: dict[str, str] = {
        "yacht_comparison": str(comparison["name"]),
        "yacht_vessel": str(vessel["name"]),
        "yacht_vessel_result": "recorded-baseline" if recorded else "measured",
    }
    if recorded:
        source = vessel.get("baseline_source", {})
        logbook = source.get("logbook")
        if isinstance(logbook, str) and logbook:
            context["yacht_baseline_logbook"] = logbook
    if other is not None:
        context["yacht_compared_against"] = str(other["name"])
        delta = comparison.get("delta")
        if isinstance(delta, dict) and str(delta.get("challenger_vessel")) == str(
            vessel["name"]
        ):
            context["yacht_resolved_delta"] = str(delta["resolved_instances_delta"])
            context["yacht_rate_delta"] = (
                f"{float(delta['resolution_rate_delta']):+.4f}"
            )
    statistics = comparison.get("statistics")
    if isinstance(statistics, dict):
        paired = statistics.get("paired")
        if isinstance(paired, dict):
            grade = paired.get("grade")
            if isinstance(grade, str) and grade:
                context["yacht_evidence_grade"] = grade
            p_value = paired.get("p_value")
            if isinstance(p_value, int | float):
                context["yacht_sign_test_p_value"] = f"{float(p_value):.6f}"
    delivery = comparison.get("delivery")
    if isinstance(delivery, dict) and str(delivery.get("vessel")) == str(
        vessel["name"]
    ):
        context["yacht_treatment_delivery"] = str(delivery.get("status"))
    return context


def _generation_config(provenance: dict[str, Any] | None) -> dict[str, Any] | None:
    if provenance is None:
        return None
    details: dict[str, str] = {}
    for key, path in (
        ("harness", ("harness", "name")),
        ("harness_version", ("harness", "version")),
        ("configured_model", ("model", "configured")),
    ):
        value = _leaf(provenance, path)
        if value is not None:
            details[key] = value
    if not details:
        return None
    return {"additional_details": details}


def _instance_rows(
    *,
    evaluation_id: str,
    model_id: str,
    course: str,
    vessel: dict[str, Any],
    comparison: dict[str, Any],
    logbook_dir: Path,
) -> list[dict[str, Any]]:
    rows = []
    outcomes = [
        *[(task_id, True) for task_id in vessel.get("resolved_ids", [])],
        *[(task_id, False) for task_id in vessel.get("unresolved_ids", [])],
    ]
    diagnostics = {
        str(entry["task"]): entry for entry in vessel.get("task_diagnostics", [])
    }
    for task_id, resolved in sorted(outcomes):
        attempt = _load_attempt(
            logbook_dir=logbook_dir,
            comparison_name=str(comparison["name"]),
            vessel_name=str(vessel["name"]),
            task_id=str(task_id),
        )
        row: dict[str, Any] = {
            "schema_version": EVERY_EVAL_EVER_INSTANCE_SCHEMA_VERSION,
            "evaluation_id": evaluation_id,
            "evaluation_result_id": (
                f"{comparison['name']}/{vessel['name']}/{METRIC_ID}"
            ),
            "model_id": model_id,
            "evaluation_name": course,
            "sample_id": str(task_id),
            "interaction_type": "agentic",
            "input": {
                "raw": _task_input(attempt, str(task_id)),
                # No reference answer exists: the task's verifier is the
                # ground truth, not a string to compare against.
                "reference": [],
            },
            "answer_attribution": [
                {
                    "turn_idx": 0,
                    "source": "grading_report",
                    "extracted_value": "resolved" if resolved else "unresolved",
                    "extraction_method": "harness_verifier",
                    "is_terminal": True,
                }
            ],
            # Agentic rows carry a transcript, not a single output.
            "output": None,
            "messages": _instance_messages(attempt, str(task_id)),
            "evaluation": _instance_evaluation(resolved, attempt),
        }
        row["evaluation"]["num_turns"] = len(row["messages"])
        token_usage = _instance_token_usage(attempt)
        if token_usage is not None:
            row["token_usage"] = token_usage
        metadata: dict[str, str] = {}
        diagnostic = diagnostics.get(str(task_id))
        if diagnostic is not None:
            reason = diagnostic.get("reason")
            if isinstance(reason, str) and reason:
                metadata["reason"] = str(reason)
        observed_tools = _observed_tools(attempt)
        if observed_tools:
            metadata["observed_tools"] = ", ".join(observed_tools)
        if metadata:
            row["metadata"] = metadata
        validate_every_eval_ever_instance_row(row)
        rows.append(row)
    return rows


def _instance_evaluation(
    resolved: bool,
    attempt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Outcome only.

    The schema's tool_calls_count means how many calls were made, but a
    yacht attempt records the *distinct tools observed*, deduplicated by
    name. Reporting one as the other would be a miscount, so the tools
    travel as row metadata instead and this field stays empty.
    """
    return {
        "score": 1.0 if resolved else 0.0,
        "is_correct": resolved,
    }


def _instance_messages(
    attempt: dict[str, Any] | None,
    task_id: str,
) -> list[dict[str, Any]]:
    prompt = task_id
    response: str | None = None
    if attempt is not None:
        attempt_prompt = attempt.get("prompt")
        if isinstance(attempt_prompt, str) and attempt_prompt:
            prompt = attempt_prompt
        attempt_response = attempt.get("agent", {}).get("response")
        if isinstance(attempt_response, str) and attempt_response:
            response = attempt_response
    return [
        {"turn_idx": 0, "role": "user", "content": prompt},
        {"turn_idx": 1, "role": "assistant", "content": response},
    ]


def _observed_tools(attempt: dict[str, Any] | None) -> list[str]:
    if attempt is None:
        return []
    tool_calls = attempt.get("agent", {}).get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [str(name) for name in tool_calls if isinstance(name, str)]


def _instance_token_usage(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
    """Only report token usage when the harness reported the split.

    The schema requires input and output counts; yacht records a total
    for some harnesses, and inventing a split to satisfy a required
    field would be an estimate wearing a measurement's clothes.
    """
    if attempt is None:
        return None
    usage = attempt.get("agent", {}).get("machine_evidence", {}).get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def _task_input(attempt: dict[str, Any] | None, task_id: str) -> str:
    if attempt is None:
        return task_id
    task = attempt.get("task")
    if not isinstance(task, dict):
        return task_id
    for key in ("problem_statement", "title"):
        value = task.get(key)
        if isinstance(value, str) and value:
            return value
    return task_id


def _load_attempt(
    *,
    logbook_dir: Path,
    comparison_name: str,
    vessel_name: str,
    task_id: str,
) -> dict[str, Any] | None:
    path = (
        logbook_dir
        / "task-attempts"
        / comparison_name
        / vessel_name
        / f"{task_id}.json"
    )
    if not path.is_file():
        return None
    try:
        return load_json_object(path, "task attempt artifact")
    except ConfigError:
        return None


def _usage_by_comparison_and_vessel(
    attempts: dict[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if attempts is None:
        return {}
    return {
        (str(comparison["name"]), str(vessel["name"])): vessel
        for comparison in attempts.get("comparisons", ())
        for vessel in comparison.get("vessels", ())
    }


def _vessel_provenance(
    vessel: dict[str, Any],
    usage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if usage is not None:
        provenance = usage.get("provenance")
        if isinstance(provenance, dict):
            return provenance
    source = vessel.get("baseline_source")
    if isinstance(source, dict):
        provenance = source.get("provenance")
        if isinstance(provenance, dict):
            return provenance
    return None


def _model_id(provenance: dict[str, Any] | None, vessel_name: str) -> str:
    model = _leaf(provenance or {}, ("model", "configured"))
    if model is None:
        raise ConfigError(
            f"Every Eval Ever export cannot determine the model for vessel "
            f"{vessel_name}: no task-attempt provenance recorded it. Export "
            "from a logbook whose attempts were recorded by this version of "
            "yacht."
        )
    return model


def _baseline_run_date(vessel: dict[str, Any]) -> str | None:
    source = vessel.get("baseline_source")
    if not isinstance(source, dict):
        return None
    run_date = source.get("run_date")
    if isinstance(run_date, str) and run_date:
        return run_date
    return None


def _run_timestamp(logbook_dir: Path) -> str | None:
    index_path = logbook_dir / RUN_INDEX_PATH
    if not index_path.is_file():
        return None
    index = load_json_object(index_path, "run index artifact")
    updated_at = index.get("updated_at")
    if isinstance(updated_at, str) and updated_at:
        return updated_at
    return None


def _sample_ids(vessel: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(task_id)
            for key in ("resolved_ids", "unresolved_ids")
            for task_id in vessel.get(key, [])
        }
    )


def _tool_labels(provenance: dict[str, Any]) -> list[str]:
    tools = provenance.get("tools")
    if not isinstance(tools, list):
        return []
    labels = []
    for entry in tools:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        version = entry.get("version")
        labels.append(f"{name}@{version}" if isinstance(version, str) else name)
    return labels


def _delivery_labels(usage: dict[str, Any]) -> list[str]:
    labels = []
    for entry in usage.get("tool_invocations", ()):
        if not isinstance(entry, dict):
            continue
        tool = entry.get("tool")
        if entry.get("status") != "measured":
            labels.append(f"{tool}: unmeasured")
            continue
        labels.append(
            f"{tool}: {entry.get('invoked_attempts')}"
            f"/{entry.get('measured_attempts')} invoked"
        )
    return labels


def _leaf(provenance: dict[str, Any], path: tuple[str, str]) -> str | None:
    section = provenance.get(path[0])
    if not isinstance(section, dict):
        return None
    value = section.get(path[1])
    if isinstance(value, str) and value:
        return value
    return None


def _detailed_reference(
    instance_path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    digest = hashlib.sha256(instance_path.read_bytes()).hexdigest()
    return {
        "format": "jsonl",
        "file_path": instance_path.name,
        "hash_algorithm": "sha256",
        "checksum": digest,
        "total_rows": len(rows),
    }


def _file_stem(evaluation_id: str) -> str:
    return "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in evaluation_id
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"{label} not found: {path}")
    return load_json_object(path, label)


def _optional_load(path: Path, label: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return load_json_object(path, label)
