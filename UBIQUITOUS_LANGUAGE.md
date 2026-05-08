# Ubiquitous Language

## Evaluation domain

| Term | Definition | Aliases to avoid |
| ---- | ---------- | ---------------- |
| **YACHT** | The platform for running reproducible comparisons of agentic coding setups. | Eval harness, testbed, platform when a more precise term is needed |
| **Course** | A benchmark suite, task set, or evaluation route that one or more vessels attempt. | Benchmark, suite, route |
| **Vessel** | A complete agentic coding setup being evaluated, including model, harness, and base configuration. | Agent, setup, runner, configuration |
| **Rigging** | The configurable enhancements attached to a vessel, such as tools, skills, prompts, memory systems, MCP servers, and policies. | Add-ons, enhancements, plugins, gear |
| **Sea Trial** | A single controlled experiment run of a vessel on a course. | Run, experiment, trial |
| **Regatta** | A comparison run that evaluates multiple vessels or rigging variants against the same course. | Comparison, batch run, tournament |
| **Wake** | The traces, telemetry, logs, artifacts, and evidence produced by a sea trial or regatta. | Trace, telemetry, logs |
| **Logbook** | The persisted store of reports, historical runs, scorecards, and supporting evidence. | Reports, history, archive |
| **Scorecard** | The final results view that compares outcomes across vessels, courses, and rigging variants. | Dashboard, leaderboard, report |

## Claims and measurements

| Term | Definition | Aliases to avoid |
| ---- | ---------- | ---------------- |
| **Claim** | A testable assertion that one vessel or rigging choice improves an outcome relative to a baseline. | Hypothesis, promise, improvement |
| **Baseline** | The reference vessel or rigging configuration used as the control for comparison. | Control, default, vanilla setup |
| **Metric** | A measured value used to evaluate a sea trial, such as score, token usage, duration, cost, or reliability. | Measurement, stat |
| **Outcome** | The interpreted result of a sea trial or regatta after metrics and evidence are evaluated. | Result, finding |

## Relationships

- A **Regatta** contains two or more **Sea Trials**.
- A **Sea Trial** runs exactly one **Vessel** against exactly one **Course**.
- A **Vessel** may have zero or more **Rigging** items.
- A **Course** may be reused across many **Regattas**.
- A **Wake** belongs to one **Sea Trial** or **Regatta**.
- A **Scorecard** summarizes one **Regatta**.
- The **Logbook** stores many **Sea Trials**, **Regattas**, **Wakes**, and **Scorecards**.
- A **Claim** is evaluated by comparing a candidate **Vessel** or **Rigging** variant against a **Baseline**.

## Example dialogue

> **Dev:** "If we want to test whether a new memory system helps, is that a new **Vessel**?"
>
> **Domain expert:** "Usually no. Treat the memory system as **Rigging** unless it changes the whole agentic setup."
>
> **Dev:** "Then the **Regatta** compares the baseline vessel against the same vessel with that rigging?"
>
> **Domain expert:** "Exactly. Each **Sea Trial** runs one variant through the same **Course**, and the **Wake** gives us the evidence behind the **Scorecard**."
>
> **Dev:** "So the **Logbook** keeps both the final scorecard and the raw wake?"
>
> **Domain expert:** "Yes. The scorecard is the summary; the wake is what lets us audit it later."

## Flagged ambiguities

- **Vessel** could mean only the agent, only the harness, or the full evaluated configuration. Canonical usage: **Vessel** means the full agentic coding setup under test.
- **Rigging** overlaps with "configuration." Canonical usage: **Rigging** means optional or swappable enhancements attached to a vessel, while base configuration belongs to the **Vessel**.
- **Course** overlaps with "benchmark." Canonical usage: **Course** is the product term; "benchmark" can be used when referring to external suites or industry language.
- **Wake** may include both raw telemetry and derived artifacts. Canonical usage: **Wake** is the full evidence bundle; derived summaries belong in the **Scorecard** or **Logbook**.
